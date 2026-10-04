"""Compile and simulate the actual HDL; this does not claim physical-board results."""
from __future__ import annotations
import ast
import hashlib
import json
import random
import shutil
import struct
import subprocess
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
REQUEST = struct.Struct(">HBHBH")
RESPONSE = struct.Struct(">HBBBBH")


class Oracle:
    """Deliberately recompute whole sums rather than mirror the HDL's running sum."""
    def __init__(self):
        self.windows = {0x11: [], 0x22: []}
        self.actions = {0x11: 0, 0x22: 0}

    def packet(self, index, slots):
        if index == 0:
            self.__init__()
        result = []
        for item, price in slots:
            window = self.windows[item]
            if index < 16:
                window.append(price)
                action = 0
            else:
                old_average = sum(window) // 16
                previous = window[-1]
                window[:] = window[1:] + [price]
                new_average = sum(window) // 16
                if previous <= old_average and price > new_average:
                    self.actions[item] = 2
                elif previous >= old_average and price < new_average:
                    self.actions[item] = 1
                action = self.actions[item]
            result.append((item, action))
        return RESPONSE.pack(index, *result[0], *result[1], 0)


def official_reference():
    # Extract only the organizer's reference class, never run its serial-port code.
    source = ROOT / "host/22_robust_uart_test.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "MovingAverageReference")
    namespace = dict(deque=deque, WINDOW_SIZE=16, ACTION_NONE=0,
                     ACTION_SELL=1, ACTION_BUY=2)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["MovingAverageReference"]


def session(a, b, seed, practice=False, start_index=0):
    rng = random.Random(seed ^ 0xA5A5A5A5)
    oracle = Oracle()
    reference = official_reference()
    refs = {0x11: reference(), 0x22: reference()}
    vectors = []
    for i, (pa, pb) in enumerate(zip(a, b)):
        index = i if i < 16 else i + start_index
        swap = (i >= 16 or not practice) and rng.random() < 0.5
        slots = [(0x11, pa), (0x22, pb)]
        if swap:
            slots.reverse()
        request = REQUEST.pack(index, *slots[0], *slots[1])
        expected = oracle.packet(index, slots)
        expected_actions = [refs[item].process(price) or 0 for item, price in slots]
        assert RESPONSE.unpack(expected)[2::2][0:2] == tuple(expected_actions)
        vectors.append((request.hex(), expected.hex()))
    return vectors


def make_vectors():
    seed = 0x57214720
    rng = random.Random(seed)
    practice = session([rng.randint(0, 100) for _ in range(100)],
                       [rng.randint(0, 100) for _ in range(100)], seed, True)
    core = list(practice)
    uart = list(practice)
    cases = [
        ([65535]*100, [0]*100),
        ([100]*16 + [101]*20 + [99]*20 + [100]*44,
         [100]*16 + [99]*20 + [101]*20 + [100]*44),
        ([0, 65535]*150, [65535, 0]*150),
        ([15]*15 + [16] + [15, 16, 14, 0, 65535]*20,
         [0]*15 + [1] + [0, 1, 2, 65535, 0]*20),
    ]
    for k, (a, b) in enumerate(cases):
        vectors = session(a, b, k)
        core.extend(vectors)
        # Full nominal UART includes >255 indices, boundaries, and session restarts.
        uart.extend(vectors)
    for seed in range(100):
        rng = random.Random(seed)
        a = [rng.randrange(65536) for _ in range(100)]
        b = [rng.randrange(65536) for _ in range(100)]
        core.extend(session(a, b, seed))
    core.extend(session(list(range(100)), list(range(100, 200)), 500,
                        start_index=65436))
    # Repeated early session resets, including reset during warm-up.
    for length in [1, 2, 15, 16, 17, 40]:
        vectors = session([length]*length, [65535-length]*length, length)
        core.extend(vectors)
        uart.extend(vectors)
    return core, uart, practice


def executable(name):
    local = ROOT / f".tools/iverilog/app/bin/{name}.exe"
    if local.exists():
        return str(local)
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Install Icarus Verilog; cannot find {name}.")
    return value


def run(command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def main():
    BUILD.mkdir(exist_ok=True)
    core, uart, practice = make_vectors()
    for name, vectors in [("core", core), ("uart", uart), ("practice", practice)]:
        (BUILD/f"{name}.txt").write_text(
            "".join(f"{request} {expected}\n" for request, expected in vectors), encoding="ascii")
    compiler, simulator = executable("iverilog"), executable("vvp")
    source = ["rtl/uart_rx.v", "rtl/uart_tx.v", "rtl/signal_engine.v", "rtl/trade_top.v"]
    results = []
    started = time.monotonic()
    for top, vectors in [("tb_engine", "core"), ("tb_uart", "practice")]:
        output = f"build/{top}.vvp"
        print(f"Testing {top} with {vectors} vectors...", flush=True)
        run([compiler, "-g2012", "-Wall", "-s", top, "-o", output, *source, f"sim/{top}.sv"])
        results.append(run([simulator, output, f"+VECTORS=build/{vectors}.txt"]))
    # Broad bit-level regression uses a shorter idle gap to save simulator time.
    # The unmodified production gap is separately checked above with all 100
    # official practice packets, including its full counter range.
    run([compiler, "-g2012", "-Wall", "-s", "tb_uart", "-Ptb_uart.GAP_CYCLES=16",
         "-o", "build/tb_uart_fast.vvp", *source, "sim/tb_uart.sv"])
    print("Testing full serial regression with shortened idle gaps...", flush=True)
    results.append(run([simulator, "build/tb_uart_fast.vvp", "+VECTORS=build/uart.txt"]))
    for bit_ns in [8510.349, 8857.710]:
        print(f"Testing host bit period {bit_ns} ns...", flush=True)
        results.append(run([simulator, "build/tb_uart_fast.vvp", "+VECTORS=build/practice.txt",
                            f"+BIT_NS={bit_ns}"]))
    report = {"status": "simulation_passed", "physical_board_tested": False,
              "core_packets": len(core), "production_uart_packets": len(practice),
              "short_gap_uart_packets": len(uart),
              "baud_offset_uart_packets": 2*len(practice), "results": results,
              "runtime_seconds": round(time.monotonic()-started, 2),
              "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                for name in source}}
    (BUILD/"simulation-report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print("RTL simulation complete. See reports/build-summary.json for separate Gowin build evidence; physical UART is not tested here.")


if __name__ == "__main__":
    main()
