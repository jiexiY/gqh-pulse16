"""Functional serial smoke test of Gowin's actual mapped circuit, not the RTL.

Uses production UART/gap settings and vendor primitive models. No SDF delay
annotation: routed timing is checked separately in Gowin, and USB needs a board.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from build_fpga import ROOT, digest, find_gowin

sys.path.insert(0, str(ROOT / "sim"))
from run_tests import Oracle, REQUEST, executable


def verify_candidate(report):
    for name, expected in report["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Build is stale: {name}")
    if digest(ROOT / report["bitstream"]) != report["bitstream_sha256"]:
        raise ValueError("Candidate bitstream changed")
    if digest(ROOT / "impl/pnr/trade_top.vo") != report["post_pnr_netlist_sha256"]:
        raise ValueError("Mapped netlist does not match the exported build")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gowin", help="Path to Gowin IDE/bin/gw_sh.exe, to locate its simlib")
    args = parser.parse_args()
    report = json.loads((ROOT / "reports/build-summary.json").read_text(encoding="utf-8"))
    verify_candidate(report)
    library = find_gowin(args.gowin).parent.parent / "simlib/gw2a/prim_sim.v"
    if not library.is_file():
        raise SystemExit(f"Vendor simulation library missing: {library}")
    oracle = Oracle()
    # Exercise BSRAM data bit 15 and the full 20-bit running sum from warm-up,
    # so mapped-read truncation cannot hide behind a low-price smoke pattern.
    prices_a = [65535] * 16 + [0, 65535, 32768, 65535, 0]
    prices_b = [0, 65535] * 8 + [65535, 0, 65535, 32768, 0]
    vectors = []
    for index, (pa, pb) in enumerate(zip(prices_a, prices_b)):
        slots = [(0x11, pa), (0x22, pb)]
        if index in (16, 19, 20):
            slots.reverse()
        request = REQUEST.pack(index, *slots[0], *slots[1])
        vectors.append(f"{request.hex()} {oracle.packet(index, slots).hex()}\n")
    vector_path = ROOT / "build/post-pnr-vectors.txt"
    vector_path.write_text("".join(vectors), encoding="ascii")
    checked_files = [ROOT / "sim/tb_uart.sv", library, vector_path]
    hashes_before = [digest(path) for path in checked_files]
    started = time.monotonic()
    output = "build/tb_post_pnr.vvp"
    subprocess.run([executable("iverilog"), "-g2012", "-DPOST_PNR", "-s", "tb_uart",
                    "-o", output, "impl/pnr/trade_top.vo", str(library), "sim/tb_uart.sv"],
                   cwd=ROOT, check=True, timeout=120)
    print("Testing 21 mapped-circuit packets with production serial timing; allow several minutes.", flush=True)
    result = subprocess.run([executable("vvp"), output, "+VECTORS=build/post-pnr-vectors.txt"],
                            cwd=ROOT, capture_output=True, text=True, timeout=1800)
    print(result.stdout)
    print(result.stderr, end="")
    (ROOT / "build/post-pnr.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode or "PASS UART: 21 packets" not in result.stdout:
        raise SystemExit("Mapped-circuit test failed. Physical board remains unverified.")
    verify_candidate(report)
    if hashes_before != [digest(path) for path in checked_files]:
        raise SystemExit("Test inputs changed during simulation; rerun before recording a pass")
    evidence = {
        "status": "post_pnr_functional_simulation_passed",
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_board_tested": False, "sdf_delay_annotation": False,
        "packets": 21, "production_gap_cycles": 13500,
        "runtime_seconds": round(time.monotonic() - started, 2),
        "coverage": ["power-on initialization", "16-packet warm-up", "BUY/SELL/hold",
                     "full-range unsigned 16-bit history reads", "maximum 20-bit running sum",
                     "swapped item slots", "false start rejection", "malformed stop-bit recovery"],
        "bitstream_sha256": report["bitstream_sha256"],
        "post_pnr_netlist_sha256": report["post_pnr_netlist_sha256"],
        "testbench_sha256": hashes_before[0], "vendor_library_sha256": hashes_before[1],
        "vectors_sha256": hashes_before[2], "result": result.stdout.strip(),
    }
    (ROOT / "reports/post-pnr-simulation.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("Mapped-circuit simulation passed. This is not a physical board result.")


if __name__ == "__main__":
    main()
