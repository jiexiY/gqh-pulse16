"""Supplemental full-range FPGA stress test, NOT organizer qualification.

No port opens without --port. Uses one serial connection for consecutive
100-packet sessions, with index zero restarting each session. No programming,
physical reset, firmware change, or nondefault serial control-line settings.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import struct
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from board_test import candidate_evidence, with_port
from build_fpga import ROOT, digest

REQUEST = struct.Struct(">HBHBH")
RESPONSE = struct.Struct(">HBBBBH")
LABEL = "Supplemental stress, NOT organizer qualification"


class Oracle:
    """Recompute both complete window sums; do not mirror the HDL datapath."""
    def __init__(self):
        self.windows = {0x11: deque(maxlen=16), 0x22: deque(maxlen=16)}
        self.actions = {0x11: 0, 0x22: 0}

    def response(self, request):
        index, item1, price1, item2, price2 = REQUEST.unpack(request)
        if index == 0:
            self.__init__()
        if {item1, item2} != {0x11, 0x22}:
            raise ValueError("Each request must contain both item IDs exactly once")
        result = []
        for item, price in ((item1, price1), (item2, price2)):
            window = self.windows[item]
            if len(window) < 16:
                window.append(price)
                action = 0
            else:
                old_average = sum(window) // 16
                previous = window[-1]
                window.append(price)
                new_average = sum(window) // 16
                if previous <= old_average and price > new_average:
                    self.actions[item] = 2
                elif previous >= old_average and price < new_average:
                    self.actions[item] = 1
                action = self.actions[item]
            result.extend((item, action))
        return RESPONSE.pack(index, *result, 0)


def make_sessions(count=10, seed=0x1F00D16B):
    if not 4 <= count <= 20:
        raise ValueError("Use 4 to 20 sessions (400 to 2,000 packets)")
    patterns = [
        ("constant_max_zero", [65535] * 100, [0] * 100, None),
        ("constant_zero_max", [0] * 100, [65535] * 100, None),
        ("alternating_extremes", [0, 65535] * 50, [65535, 0] * 50, None),
        ("rounding_and_held_actions", [15] * 15 + [16] + [15, 16, 14, 0, 65535] * 16 + [100] * 4,
         [100] * 16 + [101] * 20 + [99] * 20 + [100] * 44, None),
    ]
    for number in range(count - 4):
        session_seed = (seed + number * 0x9E3779B9) & 0xFFFFFFFF
        rng = random.Random(session_seed)
        patterns.append((f"random_fullrange_{number}",
                         [rng.randrange(65536) for _ in range(100)],
                         [rng.randrange(65536) for _ in range(100)], session_seed))
    oracle = Oracle()
    sessions = []
    for number, (name, prices_a, prices_b, session_seed) in enumerate(patterns):
        vectors = []
        for index, (pa, pb) in enumerate(zip(prices_a, prices_b)):
            slots = [(0x11, pa), (0x22, pb)]
            # Both slot orders are guaranteed even during the initial warm-up.
            if (index + number) % 2:
                slots.reverse()
            request = REQUEST.pack(index, *slots[0], *slots[1])
            vectors.append((request, oracle.response(request)))
        sessions.append({"name": name, "seed": session_seed, "vectors": vectors})
    return sessions


def run_stress(root, port, device, *, sessions=10, seed=0x1F00D16B, serial_factory=None):
    port = port.upper()
    with_port('PORT = "COM6"', port)
    if device.device.upper() != port:
        raise ValueError("Selected device does not match the requested COM port")
    if "BTHENUM" in device.hwid.upper() or "BLUETOOTH" in device.description.upper():
        raise ValueError("Bluetooth ports are not FPGA USB connections")
    vectors = make_sessions(sessions, seed)
    before = candidate_evidence(root)  # Reject stale files before acquiring serial.
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "build/board-stress" / stamp
    run_dir.mkdir(parents=True)
    csv_path = run_dir / "packets.csv"
    evidence = {
        "label": LABEL, "status": "running", "official_qualification_verified": False,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "port": port, "device": device.description, "hwid": device.hwid,
        "candidate_before": before, "candidate_after": None,
        "test_tool_sha256": {name: digest(Path(__file__).parent / name)
                             for name in ("stress_board.py", "board_test.py", "build_fpga.py")},
        "serial_settings": {"baud": 115200, "timeout_seconds": 1.0,
                            "other_settings": "pyserial defaults; no explicit control-line toggles"},
        "serial_connections_requested": 1, "runner_programmed_or_reset_board": False,
        "planned_sessions": sessions, "planned_packets": sessions * 100,
        "packets_attempted": 0, "packets_passed": 0, "sessions": [],
        "note": "All 8 response bytes including warm-up are compared. This is independent supplemental stress, not an organizer test or judging score. Local hashes do not prove the programmed image.",
    }

    def save():
        (run_dir / "results.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    save()
    print(LABEL, flush=True)
    print(f"One continuous {port} connection; {sessions * 100} packets. Results: {run_dir}", flush=True)
    latencies = []
    failure = None
    completed = False
    began = time.monotonic()
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["session", "name", "index", "request_hex",
                                                       "expected_hex", "actual_hex", "latency_us", "status"])
            writer.writeheader()
            stream.flush()
            # Exactly the same constructor defaults as the organizer scripts.
            with serial_factory(port, 115200, timeout=1.0) as serial_port:
                time.sleep(0.2)
                serial_port.reset_input_buffer()
                for number, session in enumerate(vectors):
                    if candidate_evidence(root) != before:
                        raise ValueError("Candidate changed during the stress sequence")
                    record = {"name": session["name"], "seed": session["seed"], "packets_passed": 0}
                    evidence["sessions"].append(record)
                    for index, (request, expected) in enumerate(session["vectors"]):
                        if time.monotonic() - began > 180:
                            raise TimeoutError("Stress run exceeded the 180-second overall bound")
                        t0 = time.perf_counter_ns()
                        written = serial_port.write(request)
                        actual = serial_port.read(8) if written == 8 else b""
                        latency = (time.perf_counter_ns() - t0) / 1000
                        extra_bytes = serial_port.in_waiting
                        if written != 8:
                            verdict = "PARTIAL_WRITE"
                        elif len(actual) != 8:
                            verdict = "TIMEOUT_OR_PARTIAL_RESPONSE"
                        elif actual != expected:
                            verdict = "MISMATCH"
                        elif extra_bytes:
                            verdict = "EXTRA_RESPONSE_BYTES"
                        else:
                            verdict = "PASS"
                        evidence["packets_attempted"] += 1
                        writer.writerow({"session": number, "name": session["name"], "index": index,
                                         "request_hex": request.hex(), "expected_hex": expected.hex(),
                                         "actual_hex": actual.hex(), "latency_us": f"{latency:.2f}",
                                         "status": verdict})
                        stream.flush()
                        if verdict != "PASS":
                            raise ValueError(f"Session {number} packet {index}: {verdict}; "
                                             f"expected {expected.hex()}, received {actual.hex()}, extra bytes {extra_bytes}")
                        evidence["packets_passed"] += 1
                        record["packets_passed"] += 1
                        latencies.append(latency)
                    save()
                    print(f"Session {number + 1}/{sessions} {session['name']}: 100/100 packets correct", flush=True)
            completed = evidence["packets_passed"] == sessions * 100
    except Exception as exc:
        failure = exc
        evidence["error"] = str(exc)
    finally:
        if not completed:
            failure = failure or ValueError("Stress sequence did not complete")
        try:
            evidence["candidate_after"] = candidate_evidence(root)
            evidence["candidate_unchanged"] = evidence["candidate_after"] == before
            if not evidence["candidate_unchanged"]:
                failure = failure or ValueError("Candidate changed during stress test")
        except (OSError, ValueError, KeyError) as exc:
            evidence["candidate_unchanged"] = False
            evidence["candidate_after_error"] = str(exc)
            failure = failure or exc
        evidence["status"] = "supplemental_stress_failed" if failure else "supplemental_stress_passed"
        if failure:
            evidence.setdefault("error", str(failure))
        evidence["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        evidence["runtime_seconds"] = round(time.monotonic() - began, 3)
        evidence["latency_us"] = ({"mean": statistics.mean(latencies), "median": statistics.median(latencies),
                                    "minimum": min(latencies), "maximum": max(latencies)} if latencies else None)
        if csv_path.is_file():
            evidence["packets_csv_sha256"] = digest(csv_path)
        save()
    if failure:
        raise ValueError(f"Supplemental stress stopped: {failure}. Evidence: {run_dir}") from failure
    print(f"Supplemental stress passed: {evidence['packets_passed']} packets. NOT official qualification.", flush=True)
    return run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit FPGA COM port; omission lists only")
    parser.add_argument("--sessions", type=int, default=10, choices=range(4, 21), metavar="4..20")
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0x1F00D16B)
    args = parser.parse_args()
    try:
        from serial.tools import list_ports
        devices = list(list_ports.comports())
        for device in devices:
            print(f"{device.device}: {device.description} [{device.hwid}]")
        if not args.port:
            print("No serial port opened. Supply --port COMx explicitly to run supplemental stress.")
            return
        port = args.port.upper()
        selected = next((device for device in devices if device.device.upper() == port), None)
        if selected is None:
            raise ValueError(f"{port} is not connected")
        run_stress(ROOT, port, selected, sessions=args.sessions, seed=args.seed)
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"SUPPLEMENTAL STRESS STOPPED: {exc}") from exc


if __name__ == "__main__":
    main()
