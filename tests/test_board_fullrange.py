"""Runner tests use fake processes/ports; they are NOT physical board evidence."""
import ast
import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import board_test
from build_fpga import ROOT, SOURCES, digest


GOOD = "Packets successfully received: 100\nCorrect packets: 84\nCorrect individual actions: 168/168\nTimeouts: 0\n"
DEVICE = SimpleNamespace(device="COM6", description="USB Serial Port", hwid="USB VID:PID=0403:6010")


class OrganizerFullrangeSource(unittest.TestCase):
    def test_preview_export_hash_and_truthful_provenance(self):
        name, expected = board_test.OFFICIAL["fullrange"]
        path = ROOT / "host" / name
        provenance = json.loads(path.with_suffix(".provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(digest(path), expected)
        self.assertEqual(provenance["local_export_sha256"], expected)
        self.assertIsNone(provenance["original_download_byte_sha256"])
        self.assertEqual(provenance["source_url"], board_test.FULLRANGE_SOURCE_URL)
        source = path.read_text(encoding="utf-8")
        self.assertEqual(len(source), provenance["displayed_content_verification"]["normalized_character_count"])
        self.assertEqual(len(source.split("\n")), 339)

    def test_only_documented_settings_differ_from_organizer_robust(self):
        robust = ast.parse((ROOT / "host" / board_test.OFFICIAL["robust"][0]).read_text(encoding="utf-8-sig"))
        fullrange = ast.parse((ROOT / "host" / board_test.OFFICIAL["fullrange"][0]).read_text(encoding="utf-8-sig"))
        changes = {"PRICE_MAX": 65535, "RANDOM_SEED": 0x1F00D16B,
                   "CSV_FILE": "trade_results_100_fullrange.csv",
                   "SUMMARY_FILE": "trade_summary_100_fullrange.txt"}
        robust.body[0].value.value = fullrange.body[0].value.value
        for node in robust.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in changes:
                    node.value = ast.Constant(value=changes[node.targets[0].id])
        self.assertEqual(ast.dump(robust), ast.dump(fullrange))


def make_rows():
    return [{
        "index": str(i), "rx_index": str(i),
        "tx_item1": "0x11", "rx_item1": "0x11", "tx_price1": "65535",
        "tx_item2": "0x22", "rx_item2": "0x22", "tx_price2": "0",
        "rx_action1": "NONE", "rx_action2": "NONE",
        "expected_action1": "IGNORED" if i < 16 else "NONE",
        "expected_action2": "IGNORED" if i < 16 else "NONE",
        "rx_reserved": "0x0000",
        "action1_correct": "" if i < 16 else "YES",
        "action2_correct": "" if i < 16 else "YES",
        "packet_correct": "" if i < 16 else "YES",
        "status": "IGNORED_WARMUP" if i < 16 else "CORRECT",
        "latency_us": "16000.0",
    } for i in range(100)]


def write_outputs(root, kind, rows=None):
    rows = make_rows() if rows is None else rows
    csv_name, summary_name = board_test.OUTPUTS[kind]
    with (root / csv_name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(make_rows()[0]))
        writer.writeheader()
        writer.writerows(rows)
    (root / summary_name).write_text(GOOD, encoding="utf-8")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "build" / ("fullrange-tool-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup_fixture)
        for name in SOURCES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// Synthetic test fixture, never a hardware design\n", encoding="utf-8")
        bitstream = self.root / "bitstream/trade_top.fs"
        bitstream.parent.mkdir()
        bitstream.write_text("SYNTHETIC TEST FIXTURE - NOT A BITSTREAM", encoding="utf-8")
        (self.root / "reports").mkdir()
        manifest = {
            "source_sha256": {name: digest(self.root / name) for name in SOURCES},
            "bitstream": "bitstream/trade_top.fs", "bitstream_sha256": digest(bitstream),
            "metrics": {"synthesis_total_luts": 345},
        }
        (self.root / "reports/build-summary.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "host").mkdir()
        self.official = {}
        for kind in ("quick", "robust", "fullrange"):
            name = kind + "_synthetic_test.py"
            original = self.root / "host" / name
            original.write_text('# Synthetic process fixture, never official.\nPORT = "COM6"\n', encoding="utf-8")
            self.official[kind] = (name, digest(original))

    def cleanup_fixture(self):
        target = self.root.resolve()
        base = (ROOT / "build").resolve()
        if target.parent != base or not target.name.startswith("fullrange-tool-test-") or self.root.is_symlink():
            raise RuntimeError("Refusing to remove an unexpected fixture directory")
        shutil.rmtree(target)

    def fake_run(self, command, *, cwd, **kwargs):
        kind = Path(command[-1]).name.split("_", 1)[0]
        if kind in board_test.OUTPUTS:
            write_outputs(cwd, kind)
        return SimpleNamespace(returncode=0, stdout="PASS\n" if kind == "quick" else GOOD, stderr="")

    def run_pair(self, process=None):
        with patch.object(board_test, "OFFICIAL", self.official), \
             patch.object(board_test.subprocess, "run", side_effect=process or self.fake_run) as fake, \
             contextlib.redirect_stdout(io.StringIO()):
            directory = board_test.run_tests(self.root, "COM9", DEVICE,
                                             board_test.TEST_GROUPS["qualification"], "qualification")
        return directory, fake


class FullrangeRunner(Fixture):
    def test_fullrange_stdout_requires_complete_success(self):
        self.assertTrue(board_test.test_passed("fullrange", GOOD))
        for broken in (GOOD.replace("84", "83"), GOOD.replace("100", "99"),
                       GOOD.replace("168/168", "167/168"), GOOD.replace("Timeouts: 0", "Timeouts: 1")):
            self.assertFalse(board_test.test_passed("fullrange", broken))

    def test_candidate_records_real_local_hashes_without_claiming_loaded_image(self):
        result = board_test.candidate_evidence(self.root)
        self.assertEqual(result["bitstream_sha256"], digest(self.root / "bitstream/trade_top.fs"))
        self.assertEqual(set(result["source_sha256"]), set(SOURCES))
        self.assertFalse(result["loaded_bitstream_verified"])

    def test_modified_source_or_bitstream_rejected_before_any_process(self):
        for name in ("rtl/trade_top.v", "bitstream/trade_top.fs"):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(b"modified fixture")
            with self.subTest(name=name), patch.object(board_test.subprocess, "run") as fake:
                with self.assertRaises(ValueError):
                    board_test.run_tests(self.root, "COM6", DEVICE, ["quick"], "quick")
                fake.assert_not_called()
            path.write_bytes(original)

    def test_pair_runs_robust_then_fullrange_and_records_hashes(self):
        directory, fake = self.run_pair()
        self.assertEqual(fake.call_count, 2)
        self.assertEqual([Path(c.args[0][-1]).name for c in fake.call_args_list],
                         ["robust_synthetic_test.py", "fullrange_synthetic_test.py"])
        self.assertTrue(all(c.args[0][0] == sys.executable for c in fake.call_args_list))
        evidence = json.loads((directory / "results.json").read_text())
        self.assertEqual(evidence["status"], "requested_practice_tests_passed")
        self.assertFalse(evidence["runner_programmed_or_reset_board"])
        self.assertFalse(evidence["qualification_practice"]["official_qualification_verified"])
        self.assertTrue(evidence["qualification_practice"]["local_latency_within_full_points_threshold"])
        for outcome in evidence["tests"]:
            self.assertTrue(outcome["passed"])
            self.assertEqual(outcome["packet_audit"]["packet_count"], 100)
            name, expected = self.official[outcome["test"]]
            self.assertEqual(digest(self.root / "host" / name), expected)
            self.assertEqual(outcome["executed_copy_sha256"], digest(directory / name))
            self.assertIn('PORT = "COM9"', (directory / name).read_text())

    def test_missing_fullrange_prevents_first_test(self):
        del self.official["fullrange"]
        with patch.object(board_test, "OFFICIAL", self.official), patch.object(board_test.subprocess, "run") as fake:
            with self.assertRaisesRegex(ValueError, "not been acquired"):
                board_test.run_tests(self.root, "COM6", DEVICE, ["robust", "fullrange"], "qualification")
            fake.assert_not_called()

    def test_changed_second_official_script_prevents_first_test(self):
        (self.root / "host" / self.official["fullrange"][0]).write_text("altered", encoding="utf-8")
        with patch.object(board_test, "OFFICIAL", self.official), patch.object(board_test.subprocess, "run") as fake:
            with self.assertRaisesRegex(ValueError, "Official script changed"):
                board_test.run_tests(self.root, "COM6", DEVICE, ["robust", "fullrange"], "qualification")
            fake.assert_not_called()

    def test_every_fullrange_warmup_field_is_checked(self):
        for field, value in (("rx_index", "9"), ("rx_item1", "0x22"), ("rx_action1", "BUY"),
                             ("rx_action2", "SELL"), ("rx_reserved", "0x0001")):
            with self.subTest(field=field):
                rows = make_rows()
                rows[0][field] = value
                write_outputs(self.root, "fullrange", rows)
                verdict = board_test.csv_evidence("fullrange", self.root)
                self.assertFalse(verdict["passed"])
                self.assertTrue(verdict["includes_warmup_audit"])

    def test_partial_or_bad_scored_csv_rejected_despite_success_stdout(self):
        variants = [make_rows()[:99], make_rows(), make_rows()]
        variants[1][99]["rx_action1"] = "SELL"
        variants[2][99]["latency_us"] = "nan"
        for rows in variants:
            write_outputs(self.root, "fullrange", rows)
            self.assertFalse(board_test.csv_evidence("fullrange", self.root)["passed"])

    def test_timeout_keeps_failure_evidence_and_partial_log(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 180, output=b"partial stdout", stderr=b"partial stderr")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_pair(timeout)
        directory = next((self.root / "build/board-tests").iterdir())
        evidence = json.loads((directory / "results.json").read_text())
        self.assertEqual(evidence["status"], "stopped")
        self.assertFalse(evidence["tests"][0]["passed"])
        self.assertIn("partial stdout", (directory / "timeout.log").read_text())

    def test_midrun_bitstream_change_stops_sequence(self):
        def mutate(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            (self.root / "bitstream/trade_top.fs").write_text("changed during test")
            return result
        with self.assertRaisesRegex(ValueError, "Bitstream does not match"):
            self.run_pair(mutate)
        directory = next((self.root / "build/board-tests").iterdir())
        evidence = json.loads((directory / "results.json").read_text())
        self.assertEqual(len(evidence["tests"]), 1)
        self.assertEqual(evidence["status"], "stopped")

    def test_no_port_only_lists_and_never_runs(self):
        with patch.object(sys, "argv", ["board_test.py", "--test", "qualification"]), \
             patch("serial.tools.list_ports.comports", return_value=[DEVICE]), \
             patch.object(board_test, "run_tests") as fake, contextlib.redirect_stdout(io.StringIO()):
            board_test.main()
        fake.assert_not_called()

    def test_bluetooth_rejected_without_opening_port(self):
        bluetooth = SimpleNamespace(device="COM6", description="Bluetooth Serial", hwid="BTHENUM")
        with patch.object(sys, "argv", ["board_test.py", "--port", "COM6"]), \
             patch("serial.tools.list_ports.comports", return_value=[bluetooth]), \
             patch.object(board_test, "run_tests") as fake, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, "Bluetooth"):
                board_test.main()
        fake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
