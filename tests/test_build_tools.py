"""Tooling tests only: these never access hardware and are not board evidence."""
import ast
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_fpga import PART, ROOT, digest, parse_reports, validate_metrics
from board_test import OFFICIAL, test_passed, with_port
from preflight import audit


class BuildReports(unittest.TestCase):
    def setUp(self):
        self.synthesis = '<h2><a name="usage">Resource Usage Summary</a></h2><table>'
        self.synthesis += '\n'.join(f'<td><b>{name} </b></td>\n<td>{value}</td>' for name, value in
                                   [("LUT", 345), ("Register", 444), ("ALU", 109), ("SSRAM", 8)])
        self.synthesis += '</table>'
        self.synthesis += '''
<h2><a name="utilization">Resource Utilization Summary</a></h2>
<table class="summary_table">
<tr><td class="label">Logic</td><td>503(346 LUT, 109 ALU, 8 RAM16) / 20736</td></tr>
<tr><td class="label">Register</td><td>444 / 15750</td></tr>
<tr><td class="label">BSRAM</td><td>0 / 46</td></tr>
</table>
'''
        self.timing = f'''<Tool Version>: V1.9.11.03 Education
<Part Number>: {PART}
<Numbers of Setup Violated Endpoints>:0
<Numbers of Hold Violated Endpoints>:0
1 sys_clk Base 37.037 27.000MHz
1 sys_clk 27.000(MHz) 128.568(MHz)
3. Timing Details
3.1.1 Setup Paths Table
1 29.259 launch capture
3.1.2 Hold Paths Table
1 0.385 launch capture
3.1.3 Recovery Paths Table
'''

    def metrics(self):
        return parse_reports(self.synthesis, self.timing)

    def test_parse_and_accept(self):
        metrics = self.metrics()
        self.assertEqual(metrics["synthesis_total_luts"], 345)
        self.assertEqual(metrics["synthesis_total_logic"], 503)
        self.assertEqual(metrics["synthesis_bsram_blocks"], 0)
        self.assertEqual(metrics["synthesis_ssram_blocks"], 8)
        validate_metrics(metrics, require_ranking=True)

    def test_total_logic_is_not_reconstructed_from_primitive_counts(self):
        metrics = self.metrics()
        self.assertNotEqual(metrics["synthesis_total_logic"], metrics["synthesis_total_luts"])
        self.assertNotEqual(metrics["synthesis_total_logic"],
                            metrics["synthesis_total_luts"] + metrics["synthesis_alus"]
                            + metrics["synthesis_ssram_blocks"])

    def test_bsram_is_not_ssram_and_is_not_added_to_logic(self):
        metrics = parse_reports(self.synthesis.replace("0 / 46", "2 / 46"), self.timing)
        self.assertEqual(metrics["synthesis_bsram_blocks"], 2)
        self.assertEqual(metrics["synthesis_ssram_blocks"], 8)
        self.assertEqual(metrics["synthesis_total_logic"], 503)

    def test_ranking_uses_only_utilization_section(self):
        other_table = '<table><tr><td>Logic</td><td>999 / 20736</td></tr></table>'
        self.assertEqual(parse_reports(other_table + self.synthesis, self.timing), self.metrics())

    def test_missing_ranking_resource_is_not_zero(self):
        for name in ("Logic", "BSRAM", "utilization"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_reports(self.synthesis.replace(name, "Unknown"), self.timing)

    def test_omitted_zero_use_ssram_category(self):
        without = self.synthesis.replace('<td><b>SSRAM </b></td>\n<td>8</td>', '')
        without = without.replace('503(346 LUT, 109 ALU, 8 RAM16)', '455(346 LUT, 109 ALU)')
        metrics = parse_reports(without, self.timing)
        self.assertEqual(metrics["synthesis_ssram_blocks"], 0)
        self.assertEqual(metrics["synthesis_total_logic"], 455)

    def test_omitted_ssram_but_ram16_allocation_is_not_zero(self):
        without = self.synthesis.replace('<td><b>SSRAM </b></td>\n<td>8</td>', '')
        with self.assertRaises(ValueError):
            parse_reports(without, self.timing)

    def test_malformed_ssram_category_is_not_zero(self):
        for modified in [self.synthesis.replace('SSRAM </b></td>\n<td>8', 'SSRAM </b></td>\n<td>unknown'),
                         self.synthesis.replace('SSRAM </b></td>\n<td>8', 'RAM16S4 </b></td>\n<td>8')]:
            with self.assertRaises(ValueError):
                parse_reports(modified, self.timing)

    def test_missing_usage_table_is_not_zero(self):
        with self.assertRaises(ValueError):
            parse_reports(self.synthesis.replace('name="usage"', 'name="missing"'), self.timing)

    def test_legacy_metrics_allowed_only_outside_new_build_requirement(self):
        legacy = self.metrics()
        del legacy["synthesis_total_logic"]
        del legacy["synthesis_bsram_blocks"]
        validate_metrics(legacy)
        with self.assertRaisesRegex(ValueError, "Missing ranking metric"):
            validate_metrics(legacy, require_ranking=True)

    def test_invalid_ranking_metrics_rejected(self):
        for key, value in [("synthesis_total_logic", 0), ("synthesis_total_logic", 344),
                           ("synthesis_total_logic", -1), ("synthesis_total_logic", "503"),
                           ("synthesis_bsram_blocks", -1), ("synthesis_bsram_blocks", 0.5),
                           ("synthesis_bsram_blocks", False)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_metrics(dict(self.metrics(), **{key: value}), require_ranking=True)

    def test_current_vendor_reports_parse(self):
        metrics = parse_reports((ROOT / "reports/gowin/synthesis.html").read_text(encoding="utf-8"),
                                (ROOT / "reports/gowin/timing.txt").read_text(encoding="utf-8"))
        validate_metrics(metrics, require_ranking=True)
        self.assertGreaterEqual(metrics["synthesis_total_logic"], metrics["synthesis_total_luts"])

    def test_missing_lut_is_not_zero(self):
        with self.assertRaises(ValueError):
            parse_reports(self.synthesis.replace("LUT", "Unknown"), self.timing)

    def test_timing_directory_is_not_the_report(self):
        prefixed = "Timing Report Directory\n3. Timing Details\nNote:Core Timing Report\n" + self.timing
        self.assertEqual(parse_reports(self.synthesis, prefixed), self.metrics())

    def test_each_invalid_build_rejected(self):
        for key, value in [("part_number", "wrong"), ("clock_constraint_mhz", 100),
                           ("setup_violated_endpoints", 1), ("hold_violated_endpoints", 1),
                           ("worst_setup_slack_ns", -0.1), ("worst_hold_slack_ns", -0.1),
                           ("synthesis_total_luts", 0)]:
            with self.subTest(key=key):
                metrics = self.metrics()
                metrics[key] = value
                with self.assertRaises(ValueError):
                    validate_metrics(metrics)


class BoardTools(unittest.TestCase):
    def test_official_copies_unchanged(self):
        for name, expected in OFFICIAL.values():
            self.assertEqual(digest(ROOT / "host" / name), expected)

    def test_only_port_changes(self):
        for name, _ in OFFICIAL.values():
            source = (ROOT / "host" / name).read_text(encoding="utf-8-sig")
            before, after = ast.parse(source), ast.parse(with_port(source, "com19"))
            node = next(n for n in before.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "PORT" for t in n.targets))
            node.value.value = "COM19"
            self.assertEqual(ast.dump(before), ast.dump(after))

    def test_bad_port_rejected(self):
        for port in ["COM0", "COM-1", "COM6;exit", "", "C:/file"]:
            with self.subTest(port=port), self.assertRaises(ValueError):
                with_port('PORT = "COM6"', port)

    def test_missing_and_duplicate_port_rejected(self):
        for source in ["BAUD=115200", 'PORT="COM1"\nPORT="COM2"']:
            with self.assertRaises(ValueError):
                with_port(source, "COM6")

    def test_quick_requires_explicit_pass(self):
        self.assertTrue(test_passed("quick", "idx=20 OK\nPASS\n"))
        self.assertFalse(test_passed("quick", "1 MISMATCH(ES): see above"))

    def test_robust_requires_all_packets_and_no_timeouts(self):
        good = "Packets successfully received: 100\nCorrect packets: 84\nCorrect individual actions: 168/168\nTimeouts: 0\n"
        self.assertTrue(test_passed("robust", good))
        for bad in [good.replace("84", "83"), good.replace("100", "99"),
                    good.replace("168/168", "167/168"), good.replace("Timeouts: 0", "Timeouts: 1")]:
            self.assertFalse(test_passed("robust", bad))


class ReadinessAudit(unittest.TestCase):
    def setUp(self):
        # All mutations stay in a disposable test fixture, never in candidate files.
        (ROOT / "build").mkdir(exist_ok=True)
        # Normal inherited ACLs work inside the Windows sandbox; tempfile's
        # owner-only directory ACL excludes the sandbox's restricted identity.
        self.root = ROOT / "build" / ("preflight-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.cleanup_fixture)
        self.report = json.loads((ROOT / "reports/build-summary.json").read_text(encoding="utf-8"))
        names = [*self.report["source_sha256"], self.report["bitstream"],
                 "reports/build-summary.json", "reports/rtl-simulation.json", "sim/tb_uart.sv",
                 *["reports/gowin/" + name for name in self.report["report_sha256"]],
                 *["host/" + value[0] for value in OFFICIAL.values()]]
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        # Synthetic fixture validates audit logic only, never records a real test pass.
        post = {"status": "post_pnr_functional_simulation_passed",
                "bitstream_sha256": self.report["bitstream_sha256"],
                "post_pnr_netlist_sha256": self.report["post_pnr_netlist_sha256"],
                "testbench_sha256": digest(ROOT / "sim/tb_uart.sv")}
        (self.root / "reports/post-pnr-simulation.json").write_text(json.dumps(post), encoding="utf-8")

    def cleanup_fixture(self):
        target = self.root.resolve()
        base = (ROOT / "build").resolve()
        if target.parent != base or not target.name.startswith("preflight-test-") or self.root.is_symlink():
            raise RuntimeError("Refusing to remove an unexpected fixture directory")
        shutil.rmtree(target)

    def test_consistent_fixture(self):
        self.assertEqual(audit(self.root)[0], [])

    def test_legacy_ranking_fields_derived_without_writing_manifest(self):
        self.report["metrics"].pop("synthesis_total_logic", None)
        self.report["metrics"].pop("synthesis_bsram_blocks", None)
        path = self.root / "reports/build-summary.json"
        path.write_text(json.dumps(self.report), encoding="utf-8")
        before = path.read_bytes()
        problems, summary = audit(self.root)
        expected = parse_reports((self.root / "reports/gowin/synthesis.html").read_text(encoding="utf-8"),
                                 (self.root / "reports/gowin/timing.txt").read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        self.assertEqual(summary["metrics"]["synthesis_total_logic"], expected["synthesis_total_logic"])
        self.assertEqual(summary["metrics"]["synthesis_bsram_blocks"], expected["synthesis_bsram_blocks"])
        self.assertEqual(summary["ranking_metrics_source"], "hash_verified_gowin_reports")
        self.assertEqual(path.read_bytes(), before)

    def test_self_reported_ranking_count_must_match_report(self):
        self.report["metrics"]["synthesis_total_logic"] = 99999
        (self.root / "reports/build-summary.json").write_text(json.dumps(self.report), encoding="utf-8")
        self.assertIn("Metric differs from verified Gowin reports: synthesis_total_logic", audit(self.root)[0])

    def test_unverified_report_never_supplies_ranking_counts(self):
        self.report["ranking_metrics_source"] = "hash_verified_gowin_reports"
        (self.root / "reports/build-summary.json").write_text(json.dumps(self.report), encoding="utf-8")
        with (self.root / "reports/gowin/synthesis.html").open("a", encoding="utf-8") as stream:
            stream.write("<!-- altered -->")
        problems, summary = audit(self.root)
        self.assertIn("Ranking metrics need verified synthesis and timing reports", problems)
        self.assertNotEqual(summary.get("ranking_metrics_source"), "hash_verified_gowin_reports")

    def test_changed_source_is_rejected(self):
        (self.root / "rtl/trade_top.v").write_text("// changed", encoding="utf-8")
        self.assertIn("Missing or changed: rtl/trade_top.v", audit(self.root)[0])

    def test_changed_bitstream_is_rejected(self):
        (self.root / self.report["bitstream"]).write_bytes(b"not a bitstream")
        self.assertIn("Missing or changed: bitstream/trade_top.fs", audit(self.root)[0])

    def test_missing_netlist_test_is_pending(self):
        (self.root / "reports/post-pnr-simulation.json").unlink()
        self.assertIn("Mapped-circuit simulation evidence pending", audit(self.root)[0])


if __name__ == "__main__":
    unittest.main()
