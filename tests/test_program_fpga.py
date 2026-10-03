"""Mocked programming safety tests: never open USB, JTAG, or serial devices."""
import contextlib
import io
import json
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


class PureSafetyChecks(unittest.TestCase):
    def test_default_and_help_never_call_hardware(self):
        with patch.object(tool, "run_action") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main([]), 0)
            with self.assertRaises(SystemExit) as caught:
                tool.main(["--help"])
            self.assertEqual(caught.exception.code, 0)
            run.assert_not_called()

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

    def perform(self, action="program-sram", location="273"):
        with contextlib.redirect_stdout(io.StringIO()):
            return tool.run_action(action, location, root=self.root, runner=self.runner, audit_fn=self.audit)

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
