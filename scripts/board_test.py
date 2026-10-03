"""List ports, or run the official tests with only PORT changed in a temporary copy.

No port is opened unless --port is supplied. No programming or firmware changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

from build_fpga import ROOT, SOURCES, digest

OFFICIAL = {
    "quick": ("21_quick_uart_test.py", "a2b7f96ffe1b504c4dff0a993f309442672ec6a491f6b4c326a6ddf8d7563726"),
    "robust": ("22_robust_uart_test.py", "52f3b8da200dd464f6f12be70c5b1288a35eefef9726ca9fd1fadb39a8b5264f"),
    # Verbatim Discord full-file preview export, LF-normalized. This pins the
    # local exported source, not an unavailable original download byte hash.
    "fullrange": ("22_robust_uart_test_fullrange.py", "787d67f05a2dca644f308a58fb39d02eaab49e8c11b28526a5b3cfed7c17df05"),
}
FULLRANGE_SOURCE_URL = "https://discord.com/channels/1492317189968105502/1554962057672269905/1556050530592366734"

TEST_GROUPS = {
    "quick": ["quick"],
    "robust": ["robust"],
    "fullrange": ["fullrange"],
    "both": ["quick", "robust"],
    "qualification": ["robust", "fullrange"],
    "all": ["quick", "robust", "fullrange"],
}
OUTPUTS = {
    "robust": ("trade_results_100.csv", "trade_summary_100.txt"),
    "fullrange": ("trade_results_100_fullrange.csv", "trade_summary_100_fullrange.txt"),
}


def with_port(source, port):
    port = port.upper()
    if not re.fullmatch(r"COM[1-9]\d*", port):
        raise ValueError("Use a Windows serial port such as COM6")
    result, count = re.subn(r'(?m)^PORT\s*=\s*["\'][^"\']+["\']', f'PORT = "{port}"', source)
    if count != 1:
        raise ValueError("Expected exactly one PORT assignment in official script")
    return result


def test_passed(kind, stdout):
    if kind == "quick":
        return bool(re.search(r"^PASS\s*$", stdout, re.M))
    required = [r"^Packets successfully received: 100\s*$", r"^Correct packets: 84\s*$",
                r"^Correct individual actions: 168/168\s*$", r"^Timeouts: 0\s*$"]
    return all(re.search(pattern, stdout, re.M) for pattern in required)


def candidate_evidence(root):
    """Bind a run to unchanged local build inputs, not an assumed device image."""
    report_path = root / "reports/build-summary.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sources = {name: digest(root / name) for name in SOURCES}
    if sources != report["source_sha256"]:
        raise ValueError("Sources do not match the build manifest; rebuild before board testing")
    bitstream = "bitstream/trade_top.fs"
    if report["bitstream"] != bitstream or digest(root / bitstream) != report["bitstream_sha256"]:
        raise ValueError("Bitstream does not match the build manifest")
    return {
        "source_sha256": sources,
        "bitstream": bitstream,
        "bitstream_sha256": digest(root / bitstream),
        "build_manifest_sha256": digest(report_path),
        "build_metrics": report["metrics"],
        "loaded_bitstream_verified": False,
        "loaded_bitstream_note": "Local file hashes do not establish which image is programmed on the board.",
    }


def csv_evidence(kind, run_dir):
    """Audit captured packets, including warm-up ignored by organizer scoring."""
    csv_name, summary_name = OUTPUTS[kind]
    with (run_dir / csv_name).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    issues = []
    if len(rows) != 100:
        issues.append(f"Expected 100 captured packets; got {len(rows)}")
    latencies = []
    for index, row in enumerate(rows):
        try:
            if int(row["index"]) != index or int(row["rx_index"]) != index:
                raise ValueError("wrong packet index")
            ids = [int(row[f"tx_item{slot}"], 16) for slot in (1, 2)]
            if set(ids) != {0x11, 0x22}:
                raise ValueError("invalid transmitted item IDs")
            for slot in (1, 2):
                if row[f"rx_item{slot}"] != row[f"tx_item{slot}"]:
                    raise ValueError("response item does not match slot")
                if index < 16:
                    if row[f"rx_action{slot}"] != "NONE":
                        raise ValueError("non-NONE action during warm-up")
                elif (row[f"rx_action{slot}"] != row[f"expected_action{slot}"]
                      or row[f"action{slot}_correct"] != "YES"):
                    raise ValueError("incorrect action")
            if int(row["rx_reserved"], 16) != 0:
                raise ValueError("nonzero reserved field")
            expected_status = "IGNORED_WARMUP" if index < 16 else "CORRECT"
            if row["status"] != expected_status or (index >= 16 and row["packet_correct"] != "YES"):
                raise ValueError("unsuccessful packet verdict")
            latency = float(row["latency_us"])
            if not 0 < latency < float("inf"):
                raise ValueError("invalid latency")
            latencies.append(latency)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f"Packet {index}: {exc}")
    return {
        "passed": not issues,
        "packet_count": len(rows),
        "includes_warmup_audit": True,
        "issues": issues,
        "average_latency_us": sum(latencies) / len(latencies) if latencies else None,
        "output_sha256": {name: digest(run_dir / name) for name in (csv_name, summary_name)},
    }


def run_tests(root, port, selected, kinds, mode):
    """Run selected organizer scripts sequentially; never program or reset FPGA."""
    candidate = candidate_evidence(root)
    # Validate every selected original before running even the first test.
    prepared = []
    for kind in kinds:
        if kind not in OFFICIAL:
            raise ValueError(f"Official {kind} script has not been acquired and hash-pinned yet")
        name, expected_hash = OFFICIAL[kind]
        original = root / "host" / name
        if digest(original) != expected_hash:
            raise ValueError(f"Official script changed: {name}. Restore the organizer copy before using this runner.")
        prepared.append((kind, name, expected_hash, with_port(original.read_text(encoding="utf-8-sig"), port)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "build/board-tests" / stamp
    run_dir.mkdir(parents=True)
    evidence = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running", "mode": mode, "port": port,
        "device": selected.description, "hwid": selected.hwid,
        "candidate": candidate, "tests": [],
        "runner_programmed_or_reset_board": False,
        "note": "Physical serial practice tests only. These do not verify the programmed image or establish an official judging score.",
    }

    def save():
        (run_dir / "results.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    save()
    print(f"Close Gowin Programmer and serial terminals. Results: {run_dir}")
    print("Do not unplug, reset, reprogram, or change source/build files during this sequence.")
    try:
        for kind, name, expected_hash, source in prepared:
            if candidate_evidence(root) != candidate:
                raise ValueError("Candidate changed during the physical test sequence")
            copy = run_dir / name
            copy.write_text(source, encoding="utf-8")
            outcome = {"test": kind, "passed": False, "official_source_sha256": expected_hash,
                       "executed_copy_sha256": digest(copy)}
            if kind == "fullrange":
                outcome["source_acquisition"] = {
                    "method": "Verbatim complete Discord file preview export, LF-normalized",
                    "source_url": FULLRANGE_SOURCE_URL,
                    "original_download_byte_sha256": None,
                    "note": "The pinned hash identifies the local exported source; original downloaded bytes were unavailable.",
                }
            evidence["tests"].append(outcome)
            save()
            result = subprocess.run([sys.executable, "-u", str(copy)], cwd=run_dir,
                                    capture_output=True, text=True, errors="replace", timeout=180)
            print(result.stdout)
            print(result.stderr, end="")
            log = run_dir / f"{kind}.log"
            log.write_text(result.stdout + result.stderr, encoding="utf-8")
            outcome.update(exit_code=result.returncode, log_sha256=digest(log))
            passed = result.returncode == 0 and test_passed(kind, result.stdout)
            if kind in OUTPUTS:
                outcome["packet_audit"] = csv_evidence(kind, run_dir)
                passed = passed and outcome["packet_audit"]["passed"]
            if candidate_evidence(root) != candidate:
                raise ValueError("Candidate changed during the physical test sequence")
            outcome["passed"] = passed
            save()
            if not passed:
                raise ValueError(f"{kind} test did not pass; inspect {run_dir}")
        evidence["status"] = "requested_practice_tests_passed"
        if mode in ("qualification", "all"):
            latency = next(t["packet_audit"]["average_latency_us"] for t in evidence["tests"] if t["test"] == "robust")
            evidence["qualification_practice"] = {
                "consecutive_correctness_tests_passed": True,
                "local_robust_latency_ms": latency / 1000,
                "local_latency_within_full_points_threshold": latency <= 20782.5,
                "synthesis_luts_within_full_points_threshold": candidate["build_metrics"]["synthesis_total_luts"] <= 542,
                "official_qualification_verified": False,
                "note": "Judge PC latency and hidden seeds still determine official qualification.",
            }
        evidence["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        evidence["status"] = "stopped"
        evidence["error"] = str(exc)
        if isinstance(exc, subprocess.TimeoutExpired):
            def decoded(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
            (run_dir / "timeout.log").write_text(decoded(exc.stdout) + decoded(exc.stderr), encoding="utf-8")
        save()
        raise
    print("Requested physical practice tests passed. Keep the logs and confirm the loaded bitstream.")
    return run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit FPGA COM port; omission only lists devices")
    parser.add_argument("--test", choices=list(TEST_GROUPS), default="both",
                        help="qualification runs robust then fullrange without programming or resetting")
    args = parser.parse_args()
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        for device in ports:
            print(f"{device.device}: {device.description} [{device.hwid}]")
        if not args.port:
            print("No serial port opened. Connect the board, then rerun with --port COMx.")
            return
        port = args.port.upper()
        with_port('PORT = "COM6"', port)  # Validate before any I/O.
        selected = next((p for p in ports if p.device.upper() == port), None)
        if not selected:
            raise ValueError(f"{port} is not connected")
        if "BTHENUM" in selected.hwid.upper() or "BLUETOOTH" in selected.description.upper():
            raise ValueError("This is a Bluetooth port, not the FPGA USB connection")
        run_tests(ROOT, port, selected, TEST_GROUPS[args.test], args.test)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"BOARD TEST STOPPED: {exc}") from exc


if __name__ == "__main__":
    main()
