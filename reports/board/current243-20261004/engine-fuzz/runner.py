"""Replay the independently validated 133,272-packet corpus on one exact engine.

Simulation only. Creates new artifacts under optimization-round2-audit and never
overwrites the earlier corpus, source candidates, or their reports.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = ROOT / "build/optimization-engine-fuzz/runs/20261004T122252679971Z-b9049706"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if not candidate.is_relative_to(ROOT / "build/experiments"):
        raise ValueError("Use an isolated candidate")
    engine = candidate / "rtl/signal_engine.v"
    if sha(engine) != args.expected_sha.lower():
        raise ValueError("Unexpected engine hash")
    corpus_report = json.loads((CORPUS / "report.json").read_text(encoding="utf-8"))
    if corpus_report["status"] != "both_exact_engines_passed_same_vectors":
        raise ValueError("Original corpus did not pass")
    if sha(CORPUS / "vectors.txt") != corpus_report["vectors_sha256"]:
        raise ValueError("Original vectors changed")
    if sha(CORPUS / "inputs/tb_engine.sv") != corpus_report["input_files"]["tb_engine.sv"]["sha256"]:
        raise ValueError("Original testbench changed")
    for name, entry in corpus_report["input_files"].items():
        if sha(CORPUS / "inputs" / name) != entry["sha256"]:
            raise ValueError("Original frozen corpus input changed: " + name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    folder = HERE / "engine-runs" / stamp
    folder.mkdir(parents=True, exist_ok=False)
    record = dict(status="running", physical_board_tested=False, uart_tested=False,
                  scope="Fresh engine-only RTL simulation using the previously independently crosschecked identical corpus; not new seed coverage or official qualification",
                  candidate=str(candidate), engine_sha256=sha(engine),
                  runner_sha256=sha(Path(__file__)),
                  source_corpus_report=str(CORPUS / "report.json"),
                  source_corpus_report_sha256=sha(CORPUS / "report.json"),
                  vectors_sha256=corpus_report["vectors_sha256"],
                  packet_count=corpus_report["packet_count_per_engine"],
                  testbench_sha256=sha(CORPUS / "inputs/tb_engine.sv"), stages=[])
    def save():
        (folder / "report.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    save()
    try:
        for source, name in [(engine, "signal_engine.v"), (CORPUS / "inputs/tb_engine.sv", "tb_engine.sv"),
                             (CORPUS / "vectors.txt", "vectors.txt"), (Path(__file__), "runner.py")]:
            shutil.copyfile(source, folder / name)
            if sha(source) != sha(folder / name):
                raise ValueError("Snapshot mismatch")
        compiler = ROOT / ".tools/iverilog/app/bin/iverilog.exe"
        simulator = ROOT / ".tools/iverilog/app/bin/vvp.exe"
        record["tools"] = {p.name: dict(path=str(p), sha256=sha(p)) for p in (compiler, simulator)}
        commands = [("compile", [str(compiler), "-g2012", "-Wall", "-s", "tb_engine", "-o", "engine.vvp", "signal_engine.v", "tb_engine.sv"]),
                    ("simulate", [str(simulator), "engine.vvp", "+VECTORS=vectors.txt"])]
        for label, command in commands:
            start = time.monotonic()
            result = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=240)
            log = folder / (label + ".log")
            log.write_text(result.stdout + result.stderr, encoding="utf-8")
            record["stages"].append(dict(label=label, argv=command, exit_code=result.returncode,
                                          seconds=round(time.monotonic()-start, 3), log_sha256=sha(log)))
            save()
            if result.returncode:
                raise ValueError(f"{label} failed: {log}")
            if label == "simulate":
                passes = re.findall(r"^PASS engine: (\d+) complete packet responses$", result.stdout, re.MULTILINE)
                if passes != [str(record["packet_count"])]:
                    raise ValueError("Missing exact packet-count PASS marker")
                print(result.stdout, end="")
        if sha(engine) != record["engine_sha256"] or sha(folder / "signal_engine.v") != record["engine_sha256"]:
            raise ValueError("Engine changed during verification")
        if sha(folder / "vectors.txt") != record["vectors_sha256"]:
            raise ValueError("Copied vectors changed")
        record.update(status="exact_engine_fuzz_replay_passed", original_engine_unchanged=True,
                      simulator_executable_sha256=sha(folder / "engine.vvp"),
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as exc:
        record.update(status="failed_or_interrupted", error=repr(exc))
        raise
    finally:
        save()
        print(f"Report: {folder / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
