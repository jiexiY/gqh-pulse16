"""Build with Gowin, check reports, and publish a traceable hardware-test candidate."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART = "GW2AR-LV18QN88C8/I7"
SOURCES = ["rtl/uart_rx.v", "rtl/uart_tx.v", "rtl/signal_engine.v", "rtl/trade_top.v",
           "constraints/19_tang_nano_20k.cst", "constraints/trade_top.sdc",
           "trade_top.gprj", "scripts/build_gowin.tcl"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiler_path(path):
    """Use existing Windows 8.3 aliases for legacy compiler path handling."""
    value = str(path)
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        count = ctypes.windll.kernel32.GetShortPathNameW(value, buffer, len(buffer))
        if 0 < count < len(buffer):
            return buffer.value
    return value


def find_gowin(explicit=None):
    if explicit:
        candidate = Path(explicit).resolve()
        if candidate.is_file():
            return candidate
        raise ValueError(f"Gowin compiler not found: {candidate}")
    local = ROOT / ".tools/gowin-portable/Gowin_V1.9.11.03_Education_x64/IDE/bin/gw_sh.exe"
    if local.is_file():
        return local
    on_path = shutil.which("gw_sh")
    if on_path:
        return Path(on_path)
    raise ValueError("Install Gowin Education, then pass --gowin PATH/IDE/bin/gw_sh.exe")


def capture(pattern, text, label, cast=float):
    match = re.search(pattern, text, re.I | re.S)
    if not match:
        raise ValueError(f"Missing {label} in Gowin reports; refusing to approve build")
    return cast(match.group(1))


def parse_reports(synthesis, timing):
    usage = capture(r'<a\s+name=["\']usage["\']>.*?<table\b[^>]*>(.*?)</table>',
                    synthesis, "Resource Usage Summary", str)
    def resource(name):
        # Gowin omits zero-use primitive categories. Accept absent SSRAM only
        # inside a present, fully delimited Usage table with no RAM16 entries;
        # malformed/present category rows still fail the required parser below.
        if (name == "SSRAM"
                and not re.search(r"\b(?:SSRAM|RAM16\w*)\b", usage, re.I)
                and not re.search(r"\bRAM16\w*\b", utilization, re.I)):
            return 0
        return capture(r"<b>" + re.escape(name) + r"\s*</b></td>\s*<td>(\d+)</td>",
                       usage, name, int)
    # Ranking uses the aggregate Logic allocation, NOT the primitive LUT count
    # in Resource Usage Summary. In our baseline these are 503 and 345. Read
    # the vendor total directly: do not reconstruct it from LUT/ALU/RAM counts.
    utilization = capture(
        r'<a\s+name=["\']utilization["\']>.*?<table\b[^>]*>(.*?)</table>',
        synthesis, "Resource Utilization Summary", str)

    def allocated(name):
        return capture(r'<td\b[^>]*>\s*(?:<b>)?' + re.escape(name)
                       + r'\s*(?:</b>)?\s*</td>\s*<td\b[^>]*>\s*(\d+)\s*(?:\(|/)',
                       utilization, "allocated " + name, int)
    # Gowin repeats headings in its introductory directory before the real report.
    summary = timing.split("Note:Core Timing Report", 1)[-1].split("3. Timing Details", 1)[0]
    setup_section = timing.split("3.1.1 Setup Paths Table")[-1].split("3.1.2 Hold Paths Table")[0]
    hold_section = timing.split("3.1.2 Hold Paths Table")[-1].split("3.1.3 Recovery Paths Table")[0]
    row = r"\n\s*1\s+([-\d.]+)\s+"
    return {
        "tool_version": capture(r"<Tool Version>:\s*([^\r\n]+)", summary, "version", str),
        "part_number": capture(r"<Part Number>:\s*([^\r\n]+)", summary, "part", str),
        "synthesis_total_luts": resource("LUT"),
        "synthesis_total_logic": allocated("Logic"),
        "synthesis_bsram_blocks": allocated("BSRAM"),
        "synthesis_registers": resource("Register"),
        "synthesis_alus": resource("ALU"),
        "synthesis_ssram_blocks": resource("SSRAM"),
        "clock_constraint_mhz": capture(r"sys_clk\s+Base\s+[\d.]+\s+([\d.]+)MHz", summary, "clock"),
        "reported_fmax_mhz": capture(r"sys_clk\s+[\d.]+\(MHz\)\s+([\d.]+)\(MHz\)", summary, "Fmax"),
        "setup_violated_endpoints": capture(r"<Numbers of Setup Violated Endpoints>:(\d+)", summary, "setup", int),
        "hold_violated_endpoints": capture(r"<Numbers of Hold Violated Endpoints>:(\d+)", summary, "hold", int),
        "worst_setup_slack_ns": capture(row, setup_section, "setup slack"),
        "worst_hold_slack_ns": capture(row, hold_section, "hold slack"),
    }


def validate_metrics(metrics, *, require_ranking=False):
    if metrics["part_number"] != PART:
        raise ValueError("Wrong FPGA part in report")
    if abs(metrics["clock_constraint_mhz"] - 27) > 0.001:
        raise ValueError("Clock constraint must be 27 MHz")
    if metrics["synthesis_total_luts"] <= 0:
        raise ValueError("Invalid LUT count")
    # Old manifests remain readable; every newly parsed/build report must carry
    # these fields. Preflight derives legacy fields only from verified reports.
    for key in ("synthesis_total_logic", "synthesis_bsram_blocks"):
        if key not in metrics:
            if require_ranking:
                raise ValueError(f"Missing ranking metric: {key}")
            continue
        if type(metrics[key]) is not int or metrics[key] < 0:
            raise ValueError(f"Invalid resource count: {key}")
    if "synthesis_total_logic" in metrics:
        if metrics["synthesis_total_logic"] <= 0:
            raise ValueError("Invalid total Logic count")
        if metrics["synthesis_total_logic"] < metrics["synthesis_total_luts"]:
            raise ValueError("Total Logic cannot be smaller than primitive LUT usage")
    if (metrics["setup_violated_endpoints"] or metrics["hold_violated_endpoints"]
            or metrics["worst_setup_slack_ns"] < 0 or metrics["worst_hold_slack_ns"] < 0):
        raise ValueError("Timing violation: do not program this build")


def build(gowin):
    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    before = {name: digest(ROOT / name) for name in SOURCES}
    if before["constraints/19_tang_nano_20k.cst"] != "cfa65fc9d94df4850e6849b5dd48da4fce6cdd0527cc0e30beb59df5fcf41ccf":
        raise ValueError("Organizer pin constraints changed; do not build with different pins")
    start = time.time()
    build_environment = os.environ.copy()
    build_environment["PULSE16_PROJECT_ROOT"] = compiler_path(ROOT).replace("\\", "/")
    result = subprocess.run([compiler_path(gowin), "scripts/build_gowin.tcl"], cwd=compiler_path(ROOT),
                            env=build_environment,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", timeout=600)
    print(result.stdout)
    (build_dir / "gowin-build.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode or re.search(r"^ERROR\s*\(", result.stdout, re.M):
        raise ValueError(f"Gowin failed (exit code {result.returncode}); no candidate was exported")
    if "Bitstream generation completed" not in result.stdout:
        raise ValueError("Gowin did not confirm bitstream generation")
    files = {
        "synthesis.html": ROOT / "impl/gwsynthesis/trade_top_syn.rpt.html",
        "timing.txt": ROOT / "impl/pnr/trade_top.tr",
        "place-route.txt": ROOT / "impl/pnr/trade_top.rpt.txt",
        "pins.html": ROOT / "impl/pnr/trade_top.pin.html",
    }
    bitstream = ROOT / "impl/pnr/trade_top.fs"
    netlist = ROOT / "impl/pnr/trade_top.vo"
    for path in [*files.values(), bitstream, netlist]:
        if not path.is_file() or not path.stat().st_size or path.stat().st_mtime < start - 2:
            raise ValueError(f"Missing or stale build output: {path}")
    if before != {name: digest(ROOT / name) for name in SOURCES}:
        raise ValueError("Source changed during the build; rebuild before exporting")
    metrics = parse_reports(files["synthesis.html"].read_text(encoding="utf-8"),
                            files["timing.txt"].read_text(encoding="utf-8"))
    validate_metrics(metrics, require_ranking=True)
    simulation = json.loads((build_dir / "simulation-report.json").read_text(encoding="utf-8"))
    if simulation.get("status") != "simulation_passed":
        raise ValueError("A passing RTL simulation report is required")
    for name in SOURCES[:4]:
        if simulation.get("source_sha256", {}).get(name) != before[name]:
            raise ValueError(f"RTL simulation is stale for {name}; run test.ps1 first")
    reports = ROOT / "reports/gowin"
    reports.mkdir(parents=True, exist_ok=True)
    (ROOT / "bitstream").mkdir(exist_ok=True)
    shutil.copyfile(bitstream, ROOT / "bitstream/trade_top.fs")
    for name, source in files.items():
        shutil.copyfile(source, reports / name)
    shutil.copyfile(build_dir / "gowin-build.log", reports / "build.log")
    shutil.copyfile(build_dir / "simulation-report.json", ROOT / "reports/rtl-simulation.json")
    report = {
        "status": "compiled_candidate_not_board_verified",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_board_tested": False,
        "runtime_seconds": round(time.time() - start, 2),
        "metrics": metrics,
        "warnings": re.findall(r"^WARN[^\r\n]+", result.stdout, re.M),
        "source_sha256": before,
        "bitstream": "bitstream/trade_top.fs",
        "bitstream_sha256": digest(bitstream),
        "post_pnr_netlist_sha256": digest(netlist),
        "report_sha256": {name: digest(reports / name) for name in [*files, "build.log"]},
        "timing_scope": "Internal synchronous paths at 27 MHz; not a physical UART/USB measurement",
    }
    (ROOT / "reports/build-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print("Exported bitstream/trade_top.fs. Physical board validation is still required.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gowin", help="Path to Gowin Education IDE/bin/gw_sh.exe")
    args = parser.parse_args()
    try:
        build(find_gowin(args.gowin))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"BUILD FAILED: {exc}") from exc


if __name__ == "__main__":
    main()
