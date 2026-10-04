"""Read-only portable check of archived release evidence; never touches hardware."""
import hashlib
import json
import statistics
from pathlib import Path

from preflight import audit
from board_test import candidate_evidence, OFFICIAL

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    problems, build = audit(ROOT)
    assert not problems, problems
    summary = read(ROOT / "reports/physical-verification.json")
    folder = ROOT / summary["evidence_directory"]
    index = ROOT / summary["evidence_index"]
    assert sha(index) == summary["evidence_index_sha256"]
    for name, expected in read(index).items():
        path = (folder / name).resolve()
        assert path.is_relative_to(folder.resolve()), name
        assert sha(path) == expected, name
    assert sha(ROOT / "reports/build-summary.json") == summary["build_summary_sha256"]
    assert build["bitstream_sha256"] == summary["candidate_sha256"]
    expected = candidate_evidence(ROOT)
    suite = read(folder / "suite.json")
    assert suite["status"] == "local_board_suite_passed"
    assert suite["candidate"] == build
    receipt = read(folder / "programming/receipt.json")
    assert receipt == suite["programming"]
    assert receipt["programmed_file_sha256"] == summary["candidate_sha256"]
    assert receipt["status"] == "sram_programmed_not_functionally_tested"
    assert all(receipt["programming_flags"].values())
    means = []
    for name in ["quick"] + [f"qualification-{i}" for i in range(1, 6)]:
        run = folder / name
        result = read(run / "results.json")
        assert result["status"] == "requested_practice_tests_passed"
        assert result["candidate"] == expected
        assert not result["runner_programmed_or_reset_board"]
        for test in result["tests"]:
            filename, official_sha = OFFICIAL[test["test"]]
            assert test["passed"] and test["exit_code"] == 0
            assert test["official_source_sha256"] == official_sha
            assert sha(run / filename) == test["executed_copy_sha256"]
            assert sha(run / (test["test"] + ".log")) == test["log_sha256"]
            if "packet_audit" in test:
                packet = test["packet_audit"]
                assert packet["passed"] and packet["packet_count"] == 100
                assert packet["includes_warmup_audit"]
                for filename, digest in packet["output_sha256"].items():
                    assert sha(run / filename) == digest
        if name != "quick":
            means.append(result["qualification_practice"]["local_robust_latency_ms"])
    assert suite["quick_audit"]["passed"] and suite["quick_audit"]["responses"] == 21
    assert means == summary["robust_run_average_latency_ms"]
    assert statistics.median(means) == summary["median_of_five_robust_run_means_ms"]
    packets = 21 + 5 * 200
    for name in ["stress"] + [f"soak-{i}" for i in range(1, 6)]:
        run = folder / name
        result = read(run / "results.json")
        assert result["status"] == "supplemental_stress_passed"
        assert result["candidate_before"] == result["candidate_after"] == expected
        assert result["packets_passed"] == result["packets_attempted"] == 2000
        assert not result["runner_programmed_or_reset_board"]
        assert sha(run / "packets.csv") == result["packets_csv_sha256"]
        packets += result["packets_passed"]
    assert packets == summary["total_checked_physical_responses"] == 13021
    print(f"PASS: {len(read(index))} archived artifacts hash-verified; {packets} checked physical responses bound to {summary['candidate_sha256']}.")
    print("Historical local evidence only; no new hardware run or official score.")


if __name__ == "__main__":
    main()
