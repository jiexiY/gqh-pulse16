"""Supplemental runner verification with fake serial only; not board evidence."""
import ast
import contextlib
import io
import json
import shutil
import sys
import unittest
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stress_board
from build_fpga import ROOT, SOURCES, digest

DEVICE = SimpleNamespace(device="COM6", description="USB Serial Port", hwid="USB VID:PID=0403:6010")


def organizer_reference_class():
    path = ROOT / "host/22_robust_uart_test.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MovingAverageReference")
    namespace = dict(deque=deque, WINDOW_SIZE=16, ACTION_NONE=0, ACTION_SELL=1, ACTION_BUY=2)
    # The serial code is never executed; only the isolated pure reference class.
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["MovingAverageReference"]


class FakeSerial:
    def __init__(self, corrupt_at=None, partial_at=None, extra_at=None, callback=None):
        self.reference_class = organizer_reference_class()
        self.references = {}
        self.requests = []
        self.reset_count = 0
        self.closed = False
        self.corrupt_at, self.partial_at, self.extra_at = corrupt_at, partial_at, extra_at
        self.callback = callback
        self.next_reply = b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def reset_input_buffer(self):
        self.reset_count += 1

    def write(self, request):
        self.requests.append(request)
        index, item1, price1, item2, price2 = stress_board.REQUEST.unpack(request)
        if index == 0:
            self.references = {0x11: self.reference_class(), 0x22: self.reference_class()}
        action1 = self.references[item1].process(price1) or 0
        action2 = self.references[item2].process(price2) or 0
        self.next_reply = stress_board.RESPONSE.pack(index, item1, action1, item2, action2, 0)
        if self.corrupt_at == len(self.requests):
            self.next_reply = self.next_reply[:-1] + b"\x01"
        if self.partial_at == len(self.requests):
            self.next_reply = self.next_reply[:3]
        if self.callback:
            self.callback(len(self.requests))
        return 8

    def read(self, count):
        assert count == 8
        return self.next_reply

    @property
    def in_waiting(self):
        return 1 if self.extra_at == len(self.requests) else 0


class StressVectors(unittest.TestCase):
    def test_default_1000_packets_and_seed_reproducible(self):
        sessions = stress_board.make_sessions()
        self.assertEqual(len(sessions), 10)
        self.assertTrue(all(len(session["vectors"]) == 100 for session in sessions))
        self.assertEqual(sessions, stress_board.make_sessions())
        self.assertNotEqual(sessions[4], stress_board.make_sessions(seed=42)[4])

    def test_all_vectors_match_independent_organizer_reference(self):
        fake = FakeSerial()
        for session in stress_board.make_sessions():
            for request, expected in session["vectors"]:
                fake.write(request)
                self.assertEqual(fake.read(8), expected)

    def test_extremes_swapped_warmups_and_restart_indices(self):
        sessions = stress_board.make_sessions()
        for session in sessions:
            vectors = session["vectors"]
            decoded = [stress_board.REQUEST.unpack(request) for request, _ in vectors]
            self.assertEqual([packet[0] for packet in decoded], list(range(100)))
            self.assertEqual({packet[1] for packet in decoded[:16]}, {0x11, 0x22})
            for request, response in vectors[:16]:
                self.assertEqual(stress_board.RESPONSE.unpack(response)[2::2], (0, 0))
        prices = {p for session in sessions[:3] for request, _ in session["vectors"]
                  for p in stress_board.REQUEST.unpack(request)[2::2]}
        self.assertEqual(prices, {0, 65535})

    def test_session_count_bounded(self):
        for count in (-1, 0, 3, 21, 1000):
            with self.assertRaises(ValueError):
                stress_board.make_sessions(count)


class StressRunner(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "build" / ("stress-tool-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup_fixture)
        for name in SOURCES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// Synthetic tooling fixture, not HDL", encoding="utf-8")
        target = self.root / "bitstream/trade_top.fs"
        target.parent.mkdir()
        target.write_text("SYNTHETIC TEST FIXTURE, NOT A BITSTREAM", encoding="utf-8")
        (self.root / "reports").mkdir()
        report = {"source_sha256": {name: digest(self.root / name) for name in SOURCES},
                  "bitstream": "bitstream/trade_top.fs", "bitstream_sha256": digest(target),
                  "metrics": {"synthesis_total_luts": 345}}
        (self.root / "reports/build-summary.json").write_text(json.dumps(report), encoding="utf-8")

    def cleanup_fixture(self):
        target = self.root.resolve()
        if target.parent != (ROOT / "build").resolve() or not target.name.startswith("stress-tool-test-") or self.root.is_symlink():
            raise RuntimeError("Unexpected fixture deletion target")
        shutil.rmtree(target)

    def run_fake(self, fake=None, count=4):
        device = fake or FakeSerial()
        factory = Mock(return_value=device)
        with patch.object(stress_board.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            directory = stress_board.run_stress(self.root, "COM6", DEVICE, sessions=count, serial_factory=factory)
        return directory, device, factory

    def evidence(self):
        directory = next((self.root / "build/board-stress").iterdir())
        return directory, json.loads((directory / "results.json").read_text())

    def test_single_acquisition_with_no_extra_control_line_changes(self):
        directory, fake, factory = self.run_fake(count=10)
        factory.assert_called_once_with("COM6", 115200, timeout=1.0)
        self.assertEqual(fake.reset_count, 1)  # Input-buffer flush only, never a DUT reset.
        self.assertTrue(fake.closed)
        self.assertEqual(len(fake.requests), 1000)
        indices = [stress_board.REQUEST.unpack(request)[0] for request in fake.requests]
        self.assertEqual(indices, list(range(100)) * 10)
        evidence = json.loads((directory / "results.json").read_text())
        self.assertEqual(evidence["status"], "supplemental_stress_passed")
        self.assertEqual(evidence["packets_passed"], 1000)
        self.assertTrue(evidence["candidate_unchanged"])
        self.assertEqual(evidence["candidate_before"], evidence["candidate_after"])
        self.assertFalse(evidence["official_qualification_verified"])
        self.assertFalse(evidence["runner_programmed_or_reset_board"])
        self.assertEqual(evidence["packets_csv_sha256"], digest(directory / "packets.csv"))
        self.assertEqual(len((directory / "packets.csv").read_text().splitlines()), 1001)

    def test_stale_candidate_rejected_before_opening_serial(self):
        (self.root / "rtl/trade_top.v").write_text("changed")
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "Sources do not match"):
            stress_board.run_stress(self.root, "COM6", DEVICE, serial_factory=factory)
        factory.assert_not_called()

    def test_bad_warmup_response_fails_closed_and_saves_evidence(self):
        fake = FakeSerial(corrupt_at=1)
        with self.assertRaisesRegex(ValueError, "MISMATCH"):
            self.run_fake(fake)
        directory, evidence = self.evidence()
        self.assertEqual(len(fake.requests), 1)
        self.assertTrue(fake.closed)
        self.assertEqual(evidence["status"], "supplemental_stress_failed")
        self.assertEqual(evidence["packets_passed"], 0)
        self.assertIn("MISMATCH", (directory / "packets.csv").read_text())

    def test_partial_response_stops_without_later_request(self):
        fake = FakeSerial(partial_at=17)
        with self.assertRaisesRegex(ValueError, "TIMEOUT_OR_PARTIAL_RESPONSE"):
            self.run_fake(fake)
        self.assertEqual(len(fake.requests), 17)
        self.assertEqual(self.evidence()[1]["packets_passed"], 16)

    def test_extra_bytes_fail_closed(self):
        fake = FakeSerial(extra_at=2)
        with self.assertRaisesRegex(ValueError, "EXTRA_RESPONSE_BYTES"):
            self.run_fake(fake)
        self.assertEqual(len(fake.requests), 2)

    def test_midrun_bitstream_change_cannot_be_a_pass(self):
        def mutate(count):
            if count == 1:
                (self.root / "bitstream/trade_top.fs").write_text("changed during stress")
        fake = FakeSerial(callback=mutate)
        with self.assertRaisesRegex(ValueError, "Bitstream does not match"):
            self.run_fake(fake)
        _, evidence = self.evidence()
        self.assertEqual(evidence["status"], "supplemental_stress_failed")
        self.assertFalse(evidence["candidate_unchanged"])
        self.assertLess(len(fake.requests), 400)

    def test_interruption_never_records_pass(self):
        def interrupt(count):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_fake(FakeSerial(callback=interrupt))
        self.assertEqual(self.evidence()[1]["status"], "supplemental_stress_failed")

    def test_omitted_port_lists_only(self):
        with patch.object(sys, "argv", ["stress_board.py"]), \
             patch("serial.tools.list_ports.comports", return_value=[DEVICE]), \
             patch.object(stress_board, "run_stress") as fake, contextlib.redirect_stdout(io.StringIO()):
            stress_board.main()
        fake.assert_not_called()

    def test_bluetooth_rejected_before_acquisition(self):
        device = SimpleNamespace(device="COM6", description="Bluetooth Serial", hwid="BTHENUM")
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "Bluetooth"):
            stress_board.run_stress(self.root, "COM6", device, serial_factory=factory)
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
