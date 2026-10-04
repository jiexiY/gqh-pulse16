"""Mocked programming safety tests: never open USB, JTAG, or serial devices."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import program_fpga as tool
from build_fpga import ROOT, digest

# Allow cold Windows process startup; production UART/programming limits are separate.
POWERSHELL_TEST_TIMEOUT_SECONDS = 120

SCAN = ''' Scanning!
 Target Cable: USB Debugger A/0/273/null@2.5MHz
Device Info:
 Family: GW2AR
 Name: GW2A-18C GW2AR-18C  (One of them)
 ID: 0x0000081B
 1 device(s) found!
 Cost 0.59 second(s)
'''
PROGRAM = ''' Target Cable: USB Debugger A/0/273/null@2.5MHz
 Target Device: GW2AR-18C(0x0000081B)
 Operation "SRAM Program" for device#1...
Programming...: [#########################] 100%
 User Code is: 0x0000BCCC
 Status Code is: 0x00006020
 Finished.
 Cost 4.24 second(s)
'''


@contextlib.contextmanager
def temporary_directory(parent, prefix):
    # Regular mkdir keeps Windows sandbox access; TemporaryDirectory's private
    # directory ACL can prevent the sandbox token from reopening its own files.
    parent = Path(parent).resolve()
    directory = parent / (prefix + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        target = directory.resolve()
        if target.parent != parent or not target.name.startswith(prefix) or directory.is_symlink():
            raise RuntimeError("Refusing to delete unexpected test fixture")
        shutil.rmtree(target)


class PureSafetyChecks(unittest.TestCase):
    def test_default_and_help_never_call_hardware(self):
        with patch.object(tool, "run_action") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main([]), 0)
            with self.assertRaises(SystemExit) as caught:
                tool.main(["--help"])
            self.assertEqual(caught.exception.code, 0)
            run.assert_not_called()

    def test_programmer_option_alone_and_help_never_call_hardware(self):
        with patch.object(tool, "run_action") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(["--programmer", "missing programmer.exe"]), 0)
            with self.assertRaises(SystemExit) as caught:
                tool.main(["--programmer", "missing programmer.exe", "--help"])
            self.assertEqual(caught.exception.code, 0)
            run.assert_not_called()

    def test_cli_forwards_explicit_programmer_for_each_action(self):
        programmer = str(Path("external Gowin installation") / "programmer_cli.exe")
        for action, location in [("list-cables", None), ("scan", "273"), ("program-sram", "273")]:
            args = ["--" + action, "--programmer", programmer]
            if location is not None:
                args += ["--location", location]
            with self.subTest(action=action), patch.object(tool, "run_action") as run:
                self.assertEqual(tool.main(args), 0)
                run.assert_called_once_with(action, location, programmer=programmer)

    def test_cli_without_programmer_preserves_existing_call_signature(self):
        for action, location in [("list-cables", None), ("scan", "273"), ("program-sram", "273")]:
            args = ["--" + action]
            if location is not None:
                args += ["--location", location]
            with self.subTest(action=action), patch.object(tool, "run_action") as run:
                self.assertEqual(tool.main(args), 0)
                run.assert_called_once_with(action, location)

    def test_location_required_and_operations_cannot_be_injected(self):
        with patch.object(tool, "run_action") as run, contextlib.redirect_stderr(io.StringIO()):
            for args in [["--scan"], ["--program-sram"], ["--run", "36"],
                         ["--scan", "--program-sram", "--location", "273"],
                         ["--list-cables", "--location", "273"]]:
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    tool.main(args)
            run.assert_not_called()

    def test_only_positive_decimal_locations(self):
        self.assertEqual(tool.location_number(273), "273")
        for value in [None, 0, -1, "273 --run 36", "0x111", "", "01", "273;exit"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                tool.location_number(value)

    def test_scan_requires_exact_device_and_cable(self):
        self.assertTrue(tool.scan_verified(SCAN, "273"))
        for changed in [SCAN.replace("1 device", "2 device"), SCAN.replace("GW2AR\n", "GW1N\n"),
                        SCAN.replace("0x0000081B", "0x0000081C"),
                        SCAN.replace("GW2AR-18C", "GW2AR-18"),
                        SCAN.replace("/273/", "/274/"), SCAN.replace("A/0/", "A/1/"),
                        SCAN + SCAN, SCAN.replace("1 device(s) found!", "")]:
            with self.subTest(changed=changed):
                self.assertFalse(tool.scan_verified(changed, "273"))

    def test_programming_requires_all_success_markers(self):
        self.assertTrue(all(tool.programming_flags(PROGRAM, "273").values()))
        for old, new in [("SRAM Program", "exFlash Erase,Program"), ("Finished.", ""),
                         ("100%", "99%"), ("GW2AR-18C(", "GW2A-18C("),
                         ("/273/", "/274/"), ("Cost", "ERROR Cost")]:
            with self.subTest(old=old):
                self.assertFalse(all(tool.programming_flags(PROGRAM.replace(old, new), "273").values()))

    def test_command_is_sram_only(self):
        command = tool.command_for(Path("programmer_cli.exe"), "program-sram", "273", Path("safe.fs"))
        self.assertEqual(command[command.index("--run") + 1], "2")
        self.assertEqual(command[command.index("--cable-index") + 1], "4")
        for action in ["flash", "erase", "firmware", "program-sram --run 36"]:
            with self.assertRaises(ValueError):
                tool.command_for(Path("programmer_cli.exe"), action, "273", Path("safe.fs"))

    def test_shortening_preserves_lowercase_bitstream_filename(self):
        with patch.object(tool, "compiler_path", side_effect=lambda path: str(path).upper()) as shorten:
            bitstream = Path("some-directory") / "candidate.fs"
            command = tool.command_for(Path("programmer_cli.exe"), "program-sram", "273", bitstream)
        fs_argument = command[command.index("--fsFile") + 1]
        self.assertEqual(Path(fs_argument).name, "candidate.fs")
        self.assertEqual(Path(fs_argument).suffix, ".fs")
        self.assertIn(unittest.mock.call(bitstream.parent), shorten.call_args_list)
        self.assertNotIn(unittest.mock.call(bitstream), shorten.call_args_list)

    def test_noncanonical_bitstream_leaf_rejected(self):
        for name in ["candidate.FS", "candidate.bin", "candidaté.fs"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                tool.command_for(Path("programmer_cli.exe"), "program-sram", "273", Path(name))


@unittest.skipUnless(shutil.which("pwsh") or shutil.which("powershell"), "PowerShell is not installed")
class PowerShellForwarding(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(temporary_directory(ROOT / "build", "programmer wrapper test "))
        self.wrapper = self.directory / "program-board.ps1"
        shutil.copyfile(ROOT / "program-board.ps1", self.wrapper)

    def invoke_wrapper(self, flags, programmer=None):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        # The copied wrapper has no project Python. Its fallback resolves
        # to this function, which captures argv without executing Python.
        stub = ("$ErrorActionPreference = 'Stop'; "
                "function global:python { "
                "ConvertTo-Json -InputObject @($args) -Compress; "
                "$global:LASTEXITCODE = 0 }; ")

        def quote(value):
            return "'" + str(value).replace("'", "''") + "'"

        command = stub + "& " + quote(self.wrapper) + " " + flags
        if programmer is not None:
            command += " -Programmer " + quote(programmer)
        return subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=POWERSHELL_TEST_TIMEOUT_SECONDS, shell=False)

    def test_wrapper_forwards_programmer_as_one_argument(self):
        programmer = str(self.directory / "installed Gowin" / "programmer_cli.exe")
        cases = [("", []),
                 ("-ListCables", ["--list-cables"]),
                 ("-Scan -Location 273", ["--scan", "--location", "273"]),
                 ("-ProgramSram -Location 273", ["--program-sram", "--location", "273"])]
        for flags, forwarded in cases:
            with self.subTest(flags=flags):
                completed = self.invoke_wrapper(flags, programmer)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(json.loads(completed.stdout.strip()),
                                 [str(self.directory / "scripts/program_fpga.py"),
                                  *forwarded, "--programmer", programmer])

    def test_wrapper_omitted_programmer_preserves_fallback(self):
        completed = self.invoke_wrapper("-Scan -Location 273")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip()),
                         [str(self.directory / "scripts/program_fpga.py"), "--scan", "--location", "273"])

    def test_wrapper_empty_or_whitespace_programmer_refuses_before_python(self):
        for programmer in ["", " ", "\t"]:
            with self.subTest(programmer=programmer):
                completed = self.invoke_wrapper("-ProgramSram -Location 273", programmer)
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout.strip(), "", "Mock Python must not run")
                self.assertIn("Programmer path must not be empty", completed.stderr)


class MockedProgramming(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "build" / ("program-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup_fixture)
        for name, data in [(str(tool.PROGRAMMER), b"not executable - mocked only"),
                           ("rtl/trade_top.v", b"fixture source"),
                           ("bitstream/trade_top.fs", b"fixture bitstream"),
                           ("reports/build-summary.json", b"{}")]:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.summary = {"bitstream": "bitstream/trade_top.fs",
                        "bitstream_sha256": digest(self.root / "bitstream/trade_top.fs"),
                        "source_sha256": {"rtl/trade_top.v": digest(self.root / "rtl/trade_top.v")}}
        self.audit = Mock(return_value=([], self.summary))
        self.runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, SCAN),
                                       subprocess.CompletedProcess([], 0, PROGRAM)])

    def cleanup_fixture(self):
        target = self.root.resolve()
        if target.parent != (ROOT / "build").resolve() or not target.name.startswith("program-test-") or self.root.is_symlink():
            raise RuntimeError("Refusing to delete unexpected test fixture")
        shutil.rmtree(target)

    def perform(self, action="program-sram", location="273", **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return tool.run_action(action, location, root=self.root, runner=self.runner,
                                   audit_fn=self.audit, **kwargs)

    def external_programmer(self):
        directory = self.enterContext(temporary_directory(ROOT.parent, "external Gowin installation "))
        programmer = directory / "Programmer bin" / "programmer_cli.exe"
        programmer.parent.mkdir()
        programmer.write_bytes(b"not executable - mocked only")
        self.assertFalse(programmer.resolve().is_relative_to(ROOT.resolve()))
        return programmer

    def receipt(self):
        paths = list((self.root / "build/programming").glob("*/receipt.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text(encoding="utf-8"))

    def test_complete_receipt_without_correctness_claim(self):
        result = self.perform()
        self.assertEqual(result["status"], "sram_programmed_not_functionally_tested")
        self.assertFalse(result["functional_correctness_verified"])
        self.assertEqual(result["candidate_before"], result["candidate_after"])
        self.assertEqual(result["programmed_file_sha256"], result["programmed_file_sha256_after"])
        self.assertEqual([c["exit_code"] for c in result["commands"]], [0, 0])
        self.assertTrue(all(result["programming_flags"].values()))
        self.assertEqual(result, self.receipt())
        self.assertEqual(self.audit.call_count, 3)
        for call in self.runner.call_args_list:
            self.assertIs(call.kwargs["shell"], False)
        program_command = self.runner.call_args_list[1].args[0]
        self.assertEqual(Path(program_command[program_command.index("--fsFile") + 1]).read_bytes(), b"fixture bitstream")

    def test_default_programmer_remains_project_local(self):
        self.perform("scan")
        expected = (self.root / tool.PROGRAMMER).resolve()
        command = self.runner.call_args.args[0]
        self.assertEqual(command[0], tool.compiler_path(expected))
        self.assertEqual(self.runner.call_args.kwargs["cwd"], tool.compiler_path(expected.parent))

    def test_external_programmer_with_spaces_preserves_sram_safety(self):
        programmer = self.external_programmer()
        result = self.perform(programmer=str(programmer))
        self.assertEqual(result["status"], "sram_programmed_not_functionally_tested")
        self.assertFalse(result["functional_correctness_verified"])
        self.assertEqual(self.runner.call_count, 2)
        self.assertEqual(self.audit.call_count, 3)
        for call in self.runner.call_args_list:
            self.assertEqual(call.args[0][0], tool.compiler_path(programmer.resolve()))
            self.assertEqual(call.kwargs["cwd"], tool.compiler_path(programmer.parent.resolve()))
            self.assertIs(call.kwargs["shell"], False)
        command = self.runner.call_args_list[1].args[0]
        self.assertEqual(command[command.index("--run") + 1], "2")
        self.assertEqual(command[command.index("--device") + 1], "GW2AR-18C")
        self.assertEqual(command[command.index("--location") + 1], "273")
        self.assertEqual(result, self.receipt())

    def test_relative_programmer_resolves_from_callers_working_directory(self):
        programmer = self.external_programmer()
        previous = Path.cwd()
        try:
            os.chdir(programmer.parent.parent)
            self.perform("scan", programmer=str(programmer.relative_to(Path.cwd())))
        finally:
            os.chdir(previous)
        self.assertEqual(self.runner.call_args.args[0][0], tool.compiler_path(programmer.resolve()))
        self.assertEqual(self.runner.call_args.kwargs["cwd"], tool.compiler_path(programmer.parent.resolve()))

    def test_invalid_explicit_programmer_never_falls_back_or_calls_runner(self):
        self.assertTrue((self.root / tool.PROGRAMMER).is_file())
        for programmer in [self.root / "missing programmer.exe", self.root, ""]:
            for action, location in [("list-cables", None), ("scan", "273"), ("program-sram", "273")]:
                with self.subTest(programmer=programmer, action=action), self.assertRaises(ValueError):
                    self.perform(action, location, programmer=programmer)
        self.runner.assert_not_called()
        self.audit.assert_not_called()
        self.assertFalse((self.root / "build/programming").exists())

    def test_external_programmer_still_refuses_wrong_device_id(self):
        programmer = self.external_programmer()
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, SCAN.replace("0x0000081B", "0x0000081C"))]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.perform(programmer=programmer)
        self.assertEqual(self.runner.call_count, 1)
        self.assertFalse(self.receipt()["programming_attempted"])

    def test_preflight_failure_never_touches_hardware(self):
        self.audit.return_value = (["stale simulation"], self.summary)
        with self.assertRaisesRegex(ValueError, "Preflight refused"):
            self.perform()
        self.runner.assert_not_called()
        self.assertFalse(self.receipt()["programming_attempted"])

    def test_changed_candidate_after_audit_never_touches_hardware(self):
        (self.root / "rtl/trade_top.v").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.perform()
        self.runner.assert_not_called()

    def test_wrong_scan_prevents_programming(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, SCAN.replace("1 device", "2 device"))]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.perform()
        self.assertEqual(self.runner.call_count, 1)
        self.assertFalse(self.receipt()["programming_attempted"])

    def test_scan_failure_prevents_programming(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 1, "Cable not found")]
        with self.assertRaisesRegex(ValueError, "scan did not complete"):
            self.perform()
        self.assertEqual(self.runner.call_count, 1)
        self.assertEqual(self.receipt()["commands"][0]["exit_code"], 1)

    def test_changes_during_scan_prevent_programming(self):
        def changed_scan(*args, **kwargs):
            (self.root / "reports/build-summary.json").write_bytes(b"changed manifest")
            return subprocess.CompletedProcess([], 0, SCAN)
        self.runner.side_effect = changed_scan
        with self.assertRaisesRegex(ValueError, "changed during device scan"):
            self.perform()
        self.assertEqual(self.runner.call_count, 1)

    def test_program_failure_is_recorded(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, SCAN),
                                   subprocess.CompletedProcess([], 1, "Programming failed")]
        with self.assertRaisesRegex(ValueError, "program-sram did not complete"):
            self.perform()
        record = self.receipt()
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["programming_attempted"])
        self.assertEqual(record["commands"][1]["exit_code"], 1)
        self.assertIn("candidate_after", record)
        self.assertFalse(record["programming_flags"]["finished"])

    def test_staged_bitstream_change_prevents_programming(self):
        def changed_scan(*args, **kwargs):
            stage = next((self.root / "build/programming").glob("*/candidate.fs"))
            stage.write_bytes(b"altered staged file")
            return subprocess.CompletedProcess([], 0, SCAN)
        self.runner.side_effect = changed_scan
        with self.assertRaisesRegex(ValueError, "Staged bitstream changed"):
            self.perform()
        self.assertEqual(self.runner.call_count, 1)
        self.assertFalse(self.receipt()["programming_attempted"])

    def test_changed_source_during_programming_is_not_certified(self):
        def change_during_programming(*args, **kwargs):
            if "--scan" in args[0]:
                return subprocess.CompletedProcess([], 0, SCAN)
            (self.root / "rtl/trade_top.v").write_bytes(b"new source")
            return subprocess.CompletedProcess([], 0, PROGRAM)
        self.runner.side_effect = change_during_programming
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.perform()
        record = self.receipt()
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["programming_flags"]["finished"])
        self.assertNotEqual(record["candidate_before"], record["candidate_after"])

    def test_build_specific_user_code_is_not_hardcoded(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, SCAN),
                                   subprocess.CompletedProcess([], 0, PROGRAM.replace("BCCC", "CAFE"))]
        record = self.perform()
        self.assertEqual(record["user_code"], ["0x0000CAFE"])
        self.assertEqual(record["status"], "sram_programmed_not_functionally_tested")

    def test_incomplete_success_text_is_not_pass(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, SCAN),
                                   subprocess.CompletedProcess([], 0, PROGRAM.replace("Finished.", ""))]
        with self.assertRaisesRegex(ValueError, "positively confirm"):
            self.perform()
        self.assertFalse(self.receipt()["programming_flags"]["finished"])

    def test_timeout_preserves_partial_log(self):
        self.runner.side_effect = [subprocess.TimeoutExpired("mocked", 30, output=b"Scanning!")]
        with self.assertRaisesRegex(ValueError, "scan did not complete"):
            self.perform()
        record = self.receipt()
        self.assertTrue(record["commands"][0]["timed_out"])
        self.assertEqual(record["commands"][0]["output"], "Scanning!")

    def test_permission_failure_is_logged_without_elevating(self):
        self.runner.side_effect = [PermissionError(".gowinsemi access denied")]
        with self.assertRaisesRegex(ValueError, "scan did not complete"):
            self.perform()
        self.assertIn(".gowinsemi", self.receipt()["commands"][0]["output"])
        self.assertEqual(self.runner.call_count, 1)

    def test_scan_only_never_programs_or_audits(self):
        result = self.perform("scan")
        self.assertEqual(result["status"], "expected_fpga_scanned")
        self.assertEqual(self.runner.call_count, 1)
        self.audit.assert_not_called()

    def test_cable_list_only_never_programs_or_audits(self):
        self.runner.side_effect = [subprocess.CompletedProcess([], 0, "USB Debugger A/0/273/null")]
        result = self.perform("list-cables", None)
        self.assertEqual(result["status"], "cables_listed")
        self.assertEqual(self.runner.call_args.args[0][-2:], ["--scan-cables", "F"])
        self.audit.assert_not_called()

    def test_candidate_path_cannot_escape_workspace(self):
        for name in ["../outside.fs", str(self.root.parent / "outside.fs")]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                tool.candidate_file(self.root, name)


if __name__ == "__main__":
    unittest.main()
