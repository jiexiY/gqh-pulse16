"""Read-only local readiness check. Never programs hardware or submits anything."""
from __future__ import annotations

import json

from build_fpga import ROOT, digest, parse_reports, validate_metrics
from board_test import OFFICIAL


def audit(root=ROOT):
    problems = []
    summary_path = root / "reports/build-summary.json"
    if not summary_path.is_file():
        return ["No build-summary.json; run build.ps1"], None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    # Trust must be established in this audit, never asserted by manifest text.
    summary.pop("ranking_metrics_source", None)

    def check(name, expected):
        path = root / name
        if not path.is_file() or digest(path) != expected:
            problems.append(f"Missing or changed: {name}")
            return False
        return True

    for name, expected in summary["source_sha256"].items():
        check(name, expected)
    check(summary["bitstream"], summary["bitstream_sha256"])
    verified_reports = {name: check("reports/gowin/" + name, expected)
                        for name, expected in summary["report_sha256"].items()}
    for name, expected in OFFICIAL.values():
        check("host/" + name, expected)
    try:
        validate_metrics(summary["metrics"])
        if all(verified_reports.get(name) for name in ("synthesis.html", "timing.txt")):
            parsed = parse_reports(
                (root / "reports/gowin/synthesis.html").read_text(encoding="utf-8"),
                (root / "reports/gowin/timing.txt").read_text(encoding="utf-8"))
            validate_metrics(parsed, require_ranking=True)
            for name, value in parsed.items():
                if name in summary["metrics"] and summary["metrics"][name] != value:
                    problems.append(f"Metric differs from verified Gowin reports: {name}")
            # Enrich only this in-memory copy of a legacy manifest. The candidate
            # files and manifest are never rewritten by this read-only audit.
            summary["metrics"].update(parsed)
            summary["ranking_metrics_source"] = "hash_verified_gowin_reports"
        else:
            problems.append("Ranking metrics need verified synthesis and timing reports")
    except ValueError as exc:
        problems.append(str(exc))
    rtl_path = root / "reports/rtl-simulation.json"
    if not rtl_path.is_file():
        problems.append("Missing RTL simulation evidence")
    else:
        rtl = json.loads(rtl_path.read_text(encoding="utf-8"))
        if rtl.get("status") != "simulation_passed":
            problems.append("RTL simulation did not pass")
        for name in summary["source_sha256"]:
            if name.startswith("rtl/") and rtl.get("source_sha256", {}).get(name) != summary["source_sha256"][name]:
                problems.append(f"Stale RTL simulation: {name}")
    post_path = root / "reports/post-pnr-simulation.json"
    if not post_path.is_file():
        problems.append("Mapped-circuit simulation evidence pending")
    else:
        post = json.loads(post_path.read_text(encoding="utf-8"))
        if post.get("status") != "post_pnr_functional_simulation_passed":
            problems.append("Mapped-circuit simulation did not pass")
        if post.get("bitstream_sha256") != summary["bitstream_sha256"]:
            problems.append("Mapped-circuit simulation belongs to another bitstream")
        if post.get("post_pnr_netlist_sha256") != summary["post_pnr_netlist_sha256"]:
            problems.append("Mapped-circuit simulation belongs to another netlist")
        check("sim/tb_uart.sv", post.get("testbench_sha256"))
    return problems, summary


def main():
    try:
        problems, summary = audit()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Preflight could not validate evidence: {exc}") from exc
    if summary:
        print(f"Gowin: {summary['metrics']['tool_version']}")
        if summary.get("ranking_metrics_source") == "hash_verified_gowin_reports":
            print(f"Ranking total Logic: {summary['metrics']['synthesis_total_logic']}")
            print(f"Ranking registers: {summary['metrics']['synthesis_registers']}")
            print(f"BSRAM blocks (excluded from Logic ranking): {summary['metrics']['synthesis_bsram_blocks']}")
        else:
            print("Ranking counts: NOT VERIFIED")
        print(f"Primitive synthesis LUTs (not total Logic): {summary['metrics']['synthesis_total_luts']}")
        print(f"Candidate SHA-256: {summary['bitstream_sha256']}")
    for problem in problems:
        print(f"NOT READY: {problem}")
    print("Physical board tests, team details, public repository, Devpost submission, and board return remain separate obligations.")
    print("Qualification requires official 100/100 plus the full-range 16-bit test without reprogramming.")
    print("Qualified ranking: total Logic, then registers, then median latency over 5 runs (within 5% is a tie).")
    if problems:
        raise SystemExit(1)
    print("PASS: local software candidate is internally consistent. NOT a board-ready or submitted certification.")


if __name__ == "__main__":
    main()
