"""Independent integrated UART request/response-stability and reset audit.

Simulation only. Copies inputs and writes evidence only below this directory.
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
FUZZ = ROOT / "build/optimization-engine-fuzz/runs/20261004T122252679971Z-b9049706"
RESET_PREFIX = '''
        // Independent reset tests: cancel partial RX, then cancel in-flight
        // engine work before any response. Reset deliberately invalidates it.
        send_byte(8'h12); send_byte(8'h34); send_byte(8'h11);
        @(negedge sys_clk); reset_btn=1;
        repeat(12) @(negedge sys_clk); reset_btn=0;
        #(host_bit_ns*2);
        if (dut.rx_count !== 0 || !dut.engine_ready || dut.tx_state !== 0)
            $fatal(1,"Partial-request reset did not recover idle state");
        fork
            begin
                send_byte(8'h00); send_byte(8'h00); send_byte(8'h22); send_byte(8'hff);
                send_byte(8'hff); send_byte(8'h11); send_byte(8'h00); send_byte(8'h00);
            end
            begin
                wait(dut.request_valid && dut.engine_ready);
                repeat(2) @(negedge sys_clk); reset_btn=1;
                repeat(12) @(negedge sys_clk); reset_btn=0;
            end
        join
        #(host_bit_ns*4);
        if (rx_bytes != 0 || !dut.engine_ready || dut.tx_state !== 0 || uart_tx_o !== 1)
            $fatal(1,"Canceled engine transaction produced output or remained busy");
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if not candidate.is_relative_to(ROOT / "build/experiments"):
        raise ValueError("Use a frozen isolated candidate")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    folder = HERE / "runs" / stamp
    (folder / "inputs").mkdir(parents=True, exist_ok=False)
    report = dict(status="running", candidate=str(candidate), physical_board_tested=False,
                  scope="Supplemental integrated RTL UART simulation with reset and adversarial RX during TX",
                  runner_sha256=digest(Path(__file__)), original_inputs={}, stages=[])
    def save():
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    def run(name, argv):
        start = time.monotonic()
        result = subprocess.run(argv, cwd=folder, capture_output=True, text=True, timeout=240)
        log = folder / (name + ".log")
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
        report["stages"].append(dict(name=name, argv=argv, exit_code=result.returncode,
                                     seconds=round(time.monotonic()-start, 3), log_sha256=digest(log)))
        save()
        if result.returncode:
            raise ValueError(f"{name} failed: {log}")
        return result.stdout
    save()
    try:
        inputs = {name: candidate / "rtl" / name for name in ("uart_rx.v", "uart_tx.v", "signal_engine.v", "trade_top.v")}
        inputs.update({"tb_uart.original.sv": ROOT / "sim/tb_uart.sv",
                       "top_contract_monitor.sv": HERE / "top_contract_monitor.sv",
                       "run_top_contract.py": Path(__file__)})
        for name, source in inputs.items():
            h = digest(source)
            shutil.copyfile(source, folder / "inputs" / name)
            if digest(folder / "inputs" / name) != h:
                raise ValueError("Input changed during snapshot")
            report["original_inputs"][name] = dict(path=str(source), sha256=h)
        original = (folder / "inputs/tb_uart.original.sv").read_text(encoding="utf-8")
        needle = "        #30000;\n"
        if original.count(needle) != 1:
            raise ValueError("Expected original startup marker")
        (folder / "inputs/tb_uart.sv").write_text(original.replace(needle, needle+RESET_PREFIX), encoding="utf-8")
        sessions = json.loads((FUZZ / "sessions.json").read_text(encoding="utf-8"))
        lines = (FUZZ / "vectors.txt").read_text(encoding="ascii").splitlines()
        chosen = [0, 1024, 1025, 1026, 1027, *range(1280, 1288)]
        vectors = []
        for number in chosen:
            session = sessions[number]
            length = min(session["length"], 32) if number < 1280 else session["length"]
            vectors.extend(lines[session["first_vector"]:session["first_vector"]+length])
        (folder / "vectors.txt").write_text("\n".join(vectors)+"\n", encoding="ascii")
        report.update(packets=len(vectors), source_fuzz_vectors_sha256=digest(FUZZ / "vectors.txt"),
                      selected_fuzz_sessions=chosen, vectors_sha256=digest(folder / "vectors.txt"),
                      derived_testbench_sha256=digest(folder / "inputs/tb_uart.sv"), gap_parameter=0)
        compiler = ROOT / ".tools/iverilog/app/bin/iverilog.exe"
        simulator = ROOT / ".tools/iverilog/app/bin/vvp.exe"
        run("compile", [str(compiler), "-g2012", "-Wall", "-s", "tb_uart", "-s", "top_contract_monitor",
                        "-Ptb_uart.GAP_CYCLES=0", "-o", "contract.vvp", *["inputs/"+name for name in inputs if name.endswith('.v')],
                        "inputs/tb_uart.sv", "inputs/top_contract_monitor.sv"])
        output = run("simulate", [str(simulator), "contract.vvp", "+VECTORS=vectors.txt"])
        if not re.search(rf"PASS UART: {len(vectors)} packets,", output) or "PASS contract:" not in output:
            raise ValueError("Missing required complete-pass markers")
        for name, source in inputs.items():
            expected = report["original_inputs"][name]["sha256"]
            if digest(source) != expected or digest(folder / "inputs" / name) != expected:
                raise ValueError(f"Input changed: {source}")
        report.update(status="integrated_contract_audit_passed", original_inputs_unchanged=True,
                      transcript=output, finished_at_utc=datetime.now(timezone.utc).isoformat())
        print(output, end="")
    except BaseException as exc:
        report.update(status="failed_or_interrupted", error=repr(exc))
        raise
    finally:
        save()
        print(f"Report: {folder / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
