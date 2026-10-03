"""Create a verified LOCAL candidate ZIP; never publish, submit, or certify hardware.

Only explicit project paths are included. Build tools, environments, generated
working directories, caches, credentials, and symbolic links are not packaged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from build_fpga import ROOT, digest
from preflight import audit

DIRECTORIES = {"rtl", "constraints", "host", "sim", "scripts", "tests", "reports", "bitstream"}
FILES = {"trade_top.gprj", "README.md", "CHECKLIST.md", "requirements.txt", ".gitignore", ".gitattributes"}
BLOCKED_DIRECTORIES = {".tools", ".venv", "build", "official", "impl", ".git", "__pycache__",
                       ".pytest_cache", ".mypy_cache", "node_modules", "env", "venv", "keys", "secrets"}
KEY_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".p8", ".jks", ".kdb"}


def is_link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def checked_path(root, path):
    """Reject link traversal and paths outside this exact checkout."""
    if is_link(root):
        raise ValueError("Project root may not be a symbolic link or junction")
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if is_link(current):
            raise ValueError(f"Symbolic link/junction is not allowed: {relative.as_posix()}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes the project: {relative.as_posix()}")
    return path


def private_file(name):
    value = name.casefold()
    stem = Path(value).stem
    return (value == ".env" or value.startswith(".env.") or value.endswith(".env")
            or Path(value).suffix in KEY_SUFFIXES
            or stem.lstrip(".") in {"credentials", "secrets", "secret", "key", "keys", "private_key",
                                    "private_keys", "api_key", "api_keys", "apikey", "apikeys",
                                    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "token", "tokens",
                                    "access_token", "password", "passwords"}
            or value.endswith((".pyc", ".pyo")))


def inventory(root):
    result = {}

    def visit(path):
        checked_path(root, path)
        if path.is_dir():
            if path.name.casefold() in BLOCKED_DIRECTORIES:
                return
            for child in sorted(path.iterdir()):
                visit(child)
        elif path.is_file() and not private_file(path.name):
            result[path.relative_to(root).as_posix()] = {"sha256": digest(path), "bytes": path.stat().st_size}
        elif not path.is_file():
            raise ValueError(f"Not a regular file: {path}")

    checked_path(root, root)
    for entry in sorted(root.iterdir()):
        if entry.name in DIRECTORIES or entry.name in FILES or entry.suffix.lower() == ".ps1":
            visit(entry)
    if not result:
        raise ValueError("No allowlisted project files found")
    return result


def validate_manifest_paths(root, files):
    path = root / "reports/build-summary.json"
    checked_path(root, path)
    report = json.loads(path.read_text(encoding="utf-8"))
    names = [*report["source_sha256"], report["bitstream"],
             *("reports/gowin/" + name for name in report["report_sha256"])]
    for name in names:
        posix = PurePosixPath(name)
        if (not isinstance(name, str) or "\\" in name or ":" in name or posix.is_absolute()
                or ".." in posix.parts or name != posix.as_posix() or name not in files):
            raise ValueError(f"Manifest references a non-packaged or unsafe path: {name}")
        checked_path(root, root / name)


def require_preflight(root):
    problems, summary = audit(root)
    if problems or summary is None:
        raise ValueError("Read-only preflight failed: " + "; ".join(problems or ["No summary"]))
    return summary


def verify_zip(zip_path, files):
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(files):
            raise ValueError("ZIP members differ from the allowlisted inventory")
        for name, expected in files.items():
            data = archive.read(name)
            if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError(f"ZIP byte verification failed: {name}")


def package(root=ROOT):
    root = Path(root).absolute()
    files = inventory(root)
    validate_manifest_paths(root, files)
    before = require_preflight(root)
    # Refuse changes during preflight itself, before creating any output.
    if inventory(root) != files:
        raise ValueError("Project changed during initial preflight")
    release_base = checked_path(root, root / "build/release")
    release_base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    output = release_base / stamp
    output.mkdir()
    zip_path = output / "pulse16-candidate.zip"
    manifest_path = output / "manifest.json"
    manifest = {
        "status": "packaging", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Local candidate package only; not hardware-ready certification or submission",
        "published": False, "submitted": False, "hardware_ready_certified": False,
        "archive": zip_path.name, "archive_sha256": None,
        "source_bitstream_sha256": before["bitstream_sha256"],
        "files": files, "file_count": len(files),
        "preflight_before": "passed", "preflight_after": "pending",
        "note": "Only allowlisted files were packaged. Review reports for actual physical evidence; packaging itself proves no hardware result. No external publishing or Git operations occurred.",
    }

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    save()
    completed = False
    try:
        with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, expected in files.items():
                path = checked_path(root, root / name)
                data = path.read_bytes()
                if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise ValueError(f"File changed during packaging: {name}")
                archive.writestr(name, data)
        verify_zip(zip_path, files)
        if inventory(root) != files:
            raise ValueError("Project changed while packaging")
        validate_manifest_paths(root, files)
        after = require_preflight(root)
        if after != before or inventory(root) != files:
            raise ValueError("Project or preflight changed before package completion")
        # Verify once more after the final preflight, including ZIP bytes/hash.
        verify_zip(zip_path, files)
        manifest["archive_sha256"] = digest(zip_path)
        manifest["preflight_after"] = "passed"
        manifest["status"] = "local_package_verified"
        completed = True
    except Exception as exc:
        manifest["error"] = str(exc)
        raise
    finally:
        if not completed:
            manifest["status"] = "package_failed_do_not_use"
            manifest.setdefault("error", "Packaging did not complete")
        save()
    print(f"Verified LOCAL candidate ZIP: {zip_path}")
    print(f"SHA-256: {manifest['archive_sha256']}")
    print(f"Manifest: {manifest_path}")
    print("This does not certify hardware readiness, publish a repository, or submit to Devpost.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        package()
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"LOCAL PACKAGING STOPPED: {exc}") from exc


if __name__ == "__main__":
    main()
