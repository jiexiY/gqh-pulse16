"""Explicit, SRAM-only Gowin programming with fail-closed checks and receipts.

No arguments only display help. Never installs drivers, changes registry/security
settings, opens a serial port, or exposes flash/erase/key/firmware operations.
Gowin may need permission to initialize %USERPROFILE%/.gowinsemi; this helper
does not grant that permission or elevate itself.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from build_fpga import ROOT, compiler_path, digest
from preflight import audit

DEVICE = "GW2AR-18C"
DEVICE_ID = 0x81B
CABLE_INDEX = "4"  # Verified on the Tang Nano 20K: USB Debugger A.
FREQUENCY = "2.5MHz"
PROGRAMMER = Path(".tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/Programmer/bin/programmer_cli.exe")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def location_number(value):
    if not re.fullmatch(r"[1-9][0-9]{0,9}", str(value)):
        raise ValueError("Location must be the positive decimal USB location from --list-cables")
    return str(value)


def candidate_file(root, name):
    relative = Path(name)
    root = root.resolve()
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or path == root:
        raise ValueError(f"Candidate path must remain inside the project: {name}")
    return path


def snapshot(root, summary):
    return {
        "bitstream_sha256": digest(candidate_file(root, summary["bitstream"])),
        "source_sha256": {name: digest(candidate_file(root, name))
                          for name in summary["source_sha256"]},
        "build_summary_sha256": digest(root / "reports/build-summary.json"),
    }


def checked_candidate(root, audit_fn):
    problems, summary = audit_fn(root)
    if problems or not summary:
        raise ValueError("Preflight refused programming: " + "; ".join(problems or ["No candidate"]))
    state = snapshot(root, summary)
    if (state["bitstream_sha256"] != summary["bitstream_sha256"]
            or state["source_sha256"] != summary["source_sha256"]):
        raise ValueError("Candidate changed after preflight")
    return summary, state


def selected_cable(output, location):
    matches = re.findall(r"Target Cable:\s*USB Debugger A/(\d+)/(\d+)/[^\r\n@]*@([^\r\n ]+)", output)
    return matches == [("0", str(location), FREQUENCY)]


def scan_verified(output, location):
    """Require one exact family/ID, the expected name, and the selected cable."""
    counts = re.findall(r"^\s*(\d+)\s+device\(s\) found!\s*$", output, re.M)
    families = re.findall(r"^\s*Family:\s*(\S+)\s*$", output, re.M)
    names = re.findall(r"^\s*Name:\s*([^\r\n]+)", output, re.M)
    ids = re.findall(r"^\s*ID:\s*(0x[0-9a-fA-F]+)\s*$", output, re.M)
    return (counts == ["1"] and families == ["GW2AR"] and len(names) == 1
            and DEVICE in names[0].split() and len(ids) == 1
            and int(ids[0], 16) == DEVICE_ID and selected_cable(output, location))


def programming_flags(output, location):
    return {
        "selected_cable_confirmed": selected_cable(output, location),
        "target_device_confirmed": bool(re.search(
            r"Target Device:\s*GW2AR-18C\(0x0*81[Bb]\)", output)),
        "sram_operation_confirmed": bool(re.search(
            r'^\s*Operation "SRAM Program" for device#1\.\.\.\s*$', output, re.M)),
        "progress_100_percent": bool(re.search(r"Programming[^\r\n]*\b100%", output)),
        "finished": bool(re.search(r"^\s*Finished\.\s*$", output, re.M)),
        "no_error_marker": not bool(re.search(r"\b(?:error|failed|failure)\b", output, re.I)),
    }


def command_for(programmer, action, location=None, bitstream=None):
    base = [compiler_path(programmer)]
    if action == "list-cables":
        return base + ["--scan-cables", "F"]
    location = location_number(location)
    selector = ["--cable-index", CABLE_INDEX, "--location", location, "--frequency", FREQUENCY]
    if action == "scan":
        return base + ["--scan", *selector]
    if action == "program-sram" and bitstream is not None:
        # Operation 2 is SRAM Program. No caller-controlled operation or extras.
        # Keep the original ASCII leaf and lowercase .fs extension. A fully
        # shortened Windows path produced CANDID~1.FS in a failed real attempt;
        # the canonical lowercase .fs path worked. Root cause is not proven.
        bitstream = Path(bitstream)
        if not bitstream.name.isascii() or bitstream.suffix != ".fs":
            raise ValueError("Use an ASCII bitstream filename with lowercase .fs extension")
        fs_argument = str(Path(compiler_path(bitstream.parent)) / bitstream.name)
        return base + ["--device", DEVICE, "--run", "2", "--fsFile", fs_argument, *selector]
    raise ValueError("Only cable enumeration, exact-device scan, and SRAM programming are supported")


def run_action(action, location=None, *, root=ROOT, runner=None, audit_fn=None):
    if action not in {"list-cables", "scan", "program-sram"}:
        raise ValueError("Unsupported hardware action")
    if action != "list-cables":
        location = location_number(location)
    elif location is not None:
        raise ValueError("--location is not used when listing cables")
    root = Path(root).resolve()
    programmer = root / PROGRAMMER
    if not programmer.is_file():
        raise ValueError(f"Missing installed programmer: {programmer}")
    runner = runner or subprocess.run
    audit_fn = audit_fn or audit
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    folder = root / "build/programming" / stamp
    folder.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1, "action": action, "started_at_utc": utc_now(),
        "status": "started", "location": location, "cable_index": int(CABLE_INDEX),
        "frequency": FREQUENCY, "commands": [], "programming_attempted": False,
        "functional_correctness_verified": False,
        "scope": "SRAM programming receipt only; UART/qualification tests are separate evidence.",
    }
    summary = None

    def persist():
        (folder / "receipt.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def execute(label, command, timeout):
        entry = {"label": label, "argv": command, "command_line": subprocess.list2cmdline(command),
                 "cwd": compiler_path(programmer.parent), "started_at_utc": utc_now(),
                 "timeout_seconds": timeout, "exit_code": None, "timed_out": False}
        record["commands"].append(entry)
        persist()
        try:
            result = runner(command, cwd=entry["cwd"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout,
                            shell=False)
            output = result.stdout or ""
            entry["exit_code"] = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            entry["timed_out"] = True
            entry["error"] = str(exc)
        except OSError as exc:
            output = str(exc)
            entry["error"] = str(exc)
        entry["finished_at_utc"] = utc_now()
        entry["output"] = output
        entry["log"] = label + ".log"
        if label == "program-sram":
            # Preserve diagnostic flags even for a timeout or nonzero exit.
            record["programming_flags"] = programming_flags(output, location)
            record["user_code"] = re.findall(r"User Code is:\s*(0x[0-9a-fA-F]+)", output)
            record["status_code"] = re.findall(r"Status Code is:\s*(0x[0-9a-fA-F]+)", output)
        (folder / entry["log"]).write_text(output, encoding="utf-8")
        persist()
        print(output)
        if entry["exit_code"] != 0:
            raise ValueError(f"{label} did not complete successfully; see {folder / entry['log']}")
        return output

    persist()
    try:
        if action == "program-sram":
            summary, record["candidate_before"] = checked_candidate(root, audit_fn)
            record["preflight_passed"] = True
            record["candidate_path"] = summary["bitstream"]
            # Freeze the approved bytes for the CLI, avoiding programming a
            # concurrently rebuilt candidate. Preserve the copy with its receipt.
            staged = folder / "candidate.fs"
            shutil.copyfile(candidate_file(root, summary["bitstream"]), staged)
            record["programmed_file_sha256"] = digest(staged)
            if record["programmed_file_sha256"] != record["candidate_before"]["bitstream_sha256"]:
                raise ValueError("Candidate changed while staging its bitstream")
        if action == "list-cables":
            execute("cables", command_for(programmer, action), 30)
            record["status"] = "cables_listed"
        else:
            scan = execute("scan", command_for(programmer, "scan", location), 30)
            record["scan_output"] = scan
            record["single_expected_fpga_confirmed"] = scan_verified(scan, location)
            if not record["single_expected_fpga_confirmed"]:
                raise ValueError("Scan did not identify exactly one expected GW2AR-18C at the selected cable")
            record["status"] = "expected_fpga_scanned"
            if action == "program-sram":
                _, after_scan = checked_candidate(root, audit_fn)
                if after_scan != record["candidate_before"]:
                    raise ValueError("Candidate changed during device scan; refusing programming")
                if digest(staged) != record["programmed_file_sha256"]:
                    raise ValueError("Staged bitstream changed; refusing programming")
                record["programming_attempted"] = True
                output = execute("program-sram", command_for(programmer, action, location, staged), 180)
                if not all(record["programming_flags"].values()):
                    raise ValueError("Programmer did not positively confirm complete SRAM programming")
                _, record["candidate_after"] = checked_candidate(root, audit_fn)
                record["programmed_file_sha256_after"] = digest(staged)
                if (record["candidate_after"] != record["candidate_before"]
                        or record["programmed_file_sha256_after"] != record["programmed_file_sha256"]):
                    raise ValueError("Candidate or staged bitstream changed during programming")
                record["status"] = "sram_programmed_not_functionally_tested"
        return record
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        raise ValueError(f"{exc}\nReceipt: {folder / 'receipt.json'}") from exc
    finally:
        if summary is not None and "candidate_after" not in record:
            try:
                record["candidate_after"] = snapshot(root, summary)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                record["candidate_after_error"] = str(exc)
        record["finished_at_utc"] = utc_now()
        persist()
        print(f"Receipt: {folder / 'receipt.json'}")
        print("This is NOT proof of UART correctness or a qualification pass.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_mutually_exclusive_group()
    choices.add_argument("--list-cables", action="store_true", help="Explicitly enumerate USB download cables")
    choices.add_argument("--scan", action="store_true", help="Explicitly identify one expected FPGA using JTAG")
    choices.add_argument("--program-sram", action="store_true", help="Preflight, scan, then load approved SRAM bitstream")
    parser.add_argument("--location", type=location_number, help="Exact decimal USB location from --list-cables")
    args = parser.parse_args(argv)
    action = next((name for name in ("list-cables", "scan", "program-sram")
                   if getattr(args, name.replace("-", "_"))), None)
    if action is None:
        parser.print_help()
        return 0
    if action != "list-cables" and args.location is None:
        parser.error("--scan and --program-sram require an explicit --location")
    if action == "list-cables" and args.location is not None:
        parser.error("--location is not used with --list-cables")
    try:
        run_action(action, args.location)
    except (OSError, ValueError) as exc:
        print(f"PROGRAMMING STOPPED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
