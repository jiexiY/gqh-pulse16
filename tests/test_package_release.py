"""Local packaging unit tests use disposable fixtures, never candidate artifacts."""
import contextlib
import io
import json
import shutil
import sys
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_release
from build_fpga import ROOT, digest


class LocalPackaging(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "build" / ("package-tool-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup_fixture)
        for name, content in {
            "rtl/top.v": b"module top;\r\n// mixed LF\nendmodule\r\n",
            "bitstream/trade_top.fs": b"SYNTHETIC TEST FIXTURE - NOT A BITSTREAM\r\n",
            "README.md": b"Synthetic README\r\n",
            "reports/physical-board/results.json": b'{"fixture":true}\n',
            "build.ps1": b"# synthetic build helper\n",
            ".gitattributes": b"* -text\n",
            "scripts/allowed.py": b"# included test fixture\n",
        }.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.summary = {
            "source_sha256": {"rtl/top.v": digest(self.root / "rtl/top.v")},
            "bitstream": "bitstream/trade_top.fs",
            "bitstream_sha256": digest(self.root / "bitstream/trade_top.fs"),
            "report_sha256": {}, "metrics": {"synthesis_total_logic": 421},
        }
        self.write_manifest()

    def write_manifest(self):
        (self.root / "reports/build-summary.json").write_text(json.dumps(self.summary), encoding="utf-8")

    def cleanup_fixture(self):
        target = self.root.resolve()
        if target.parent != (ROOT / "build").resolve() or not target.name.startswith("package-tool-test-") or self.root.is_symlink():
            raise RuntimeError("Unexpected fixture deletion target")
        shutil.rmtree(target)

    def run_package(self):
        with patch.object(package_release, "audit", return_value=([], self.summary)) as preflight, \
             contextlib.redirect_stdout(io.StringIO()):
            output = package_release.package(self.root)
        self.assertEqual(preflight.call_count, 2)
        return output

    def output_manifest(self):
        output = next((self.root / "build/release").iterdir())
        return output, json.loads((output / "manifest.json").read_text())

    def test_roundtrip_preserves_mixed_newlines_and_physical_evidence(self):
        output = self.run_package()
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(set(p.name for p in output.iterdir()), {"manifest.json", "pulse16-candidate.zip"})
        self.assertEqual(manifest["status"], "local_package_verified")
        self.assertEqual(manifest["archive_sha256"], digest(output / manifest["archive"]))
        self.assertFalse(manifest["published"])
        self.assertFalse(manifest["submitted"])
        self.assertFalse(manifest["hardware_ready_certified"])
        self.assertEqual(manifest["preflight_before"], "passed")
        self.assertEqual(manifest["preflight_after"], "passed")
        with zipfile.ZipFile(output / manifest["archive"]) as archive:
            self.assertEqual(archive.read("rtl/top.v"), (self.root / "rtl/top.v").read_bytes())
            self.assertIn("reports/physical-board/results.json", archive.namelist())
            for name in archive.namelist():
                self.assertEqual(archive.read(name), (self.root / name).read_bytes())

    def test_allowlist_excludes_tools_working_files_and_secrets(self):
        excluded = [".tools/tool.exe", ".venv/python.exe", "build/private.txt", "official/x.txt",
                    "impl/x.txt", ".git/config", "unlisted.txt", "reports/__pycache__/x.pyc",
                    "scripts/.env", "scripts/.env.local", "reports/keys/signing.txt",
                    "host/private_key.pem", "host/keys.json", "host/.credentials", "host/token.txt"]
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("SYNTHETIC EXCLUDED FIXTURE")
        output = self.run_package()
        with zipfile.ZipFile(output / "pulse16-candidate.zip") as archive:
            self.assertFalse(set(excluded).intersection(archive.namelist()))
            self.assertEqual(set(archive.namelist()), set(package_release.inventory(self.root)))

    def test_initial_preflight_failure_creates_no_package(self):
        with patch.object(package_release, "audit", return_value=(["Synthetic stale evidence"], self.summary)):
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                package_release.package(self.root)
        self.assertFalse((self.root / "build/release").exists())

    def test_changed_during_initial_preflight_creates_no_package(self):
        def changing_audit(root):
            (root / "README.md").write_text("changed during audit")
            return [], self.summary
        with patch.object(package_release, "audit", side_effect=changing_audit):
            with self.assertRaisesRegex(ValueError, "changed during initial"):
                package_release.package(self.root)
        self.assertFalse((self.root / "build/release").exists())

    def test_final_preflight_failure_marks_package_do_not_use(self):
        with patch.object(package_release, "audit", side_effect=[([], self.summary), (["late change"], self.summary)]):
            with self.assertRaisesRegex(ValueError, "late change"):
                package_release.package(self.root)
        _, manifest = self.output_manifest()
        self.assertEqual(manifest["status"], "package_failed_do_not_use")
        self.assertIsNone(manifest["archive_sha256"])

    def test_midpackaging_change_is_rejected(self):
        verifier = package_release.verify_zip
        def verify_then_mutate(path, files):
            verifier(path, files)
            (self.root / "README.md").write_text("changed after ZIP bytes captured")
        with patch.object(package_release, "audit", return_value=([], self.summary)), \
             patch.object(package_release, "verify_zip", side_effect=verify_then_mutate):
            with self.assertRaisesRegex(ValueError, "changed while packaging"):
                package_release.package(self.root)
        self.assertEqual(self.output_manifest()[1]["status"], "package_failed_do_not_use")

    def test_linked_input_and_output_are_refused(self):
        actual = package_release.is_link
        for linked in ("top.v", "build"):
            with self.subTest(linked=linked), \
                 patch.object(package_release, "is_link", side_effect=lambda p: p.name == linked or actual(p)), \
                 patch.object(package_release, "audit", return_value=([], self.summary)):
                with self.assertRaisesRegex(ValueError, "link"):
                    package_release.package(self.root)

    def test_manifest_path_escape_is_rejected_before_preflight(self):
        for name in ("../outside.key", "/absolute/path", "C:/outside.key", "rtl/../top.v", "rtl\\top.v"):
            with self.subTest(name=name):
                self.summary["source_sha256"] = {name: "not-a-real-hash"}
                self.write_manifest()
                with patch.object(package_release, "audit") as preflight:
                    with self.assertRaisesRegex(ValueError, "unsafe path"):
                        package_release.package(self.root)
                    preflight.assert_not_called()

    def test_changed_zip_bytes_or_members_fail_verification(self):
        output = self.run_package()
        manifest = json.loads((output / "manifest.json").read_text())
        archive_path = output / manifest["archive"]
        with zipfile.ZipFile(archive_path, "a") as archive:
            archive.writestr("unexpected.txt", b"not allowlisted")
        with self.assertRaisesRegex(ValueError, "ZIP members differ"):
            package_release.verify_zip(archive_path, manifest["files"])

    def test_runs_do_not_overwrite_previous_package(self):
        first = self.run_package()
        before = digest(first / "pulse16-candidate.zip")
        second = self.run_package()
        self.assertNotEqual(first, second)
        self.assertEqual(digest(first / "pulse16-candidate.zip"), before)


if __name__ == "__main__":
    unittest.main()
