#!/usr/bin/env python3
"""Enforce least-privilege permissions after every other source patch has run."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def project_root(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_symlink():
        raise SystemExit(f"Refusing symbolic-link project root: {candidate}")
    try:
        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"Project directory cannot be resolved: {exc}") from exc
    if not root.is_dir():
        raise SystemExit(f"Project path is not a directory: {root}")
    return root


def reject_symlink_components(root: Path, target: Path) -> None:
    """Reject symlinks in every project-relative component before reading or writing."""
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"Refusing path outside project root: {target}") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise SystemExit(f"Refusing symbolic link in project path: {current}")


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a regular file atomically without following a destination symlink."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        if path.exists():
            os.chmod(temporary_name, stat.S_IMODE(path.stat().st_mode))
        else:
            os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


PROJECT = project_root(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = PROJECT / "android/app/src/main/AndroidManifest.xml"
REPORT = PROJECT / "torqscan-patch-report.json"

# Validate every destination before changing either file. Path.is_file() alone
# follows symlinks and would allow an extracted archive to redirect these writes.
reject_symlink_components(PROJECT, MANIFEST)
reject_symlink_components(PROJECT, REPORT)
if not MANIFEST.is_file():
    raise SystemExit(f"Android manifest missing: {MANIFEST}")
if REPORT.exists() and not REPORT.is_file():
    raise SystemExit(f"Patch report is not a regular file: {REPORT}")

content = MANIFEST.read_text(encoding="utf-8")
root_match = re.search(r"<manifest\\b[^>]*>", content, re.S)
if root_match is None:
    raise SystemExit("Android manifest root element not found")
root_tag = root_match.group(0)
if not re.search(r"\\bxmlns:tools\\s*=", root_tag):
    updated_root = root_tag[:-1] + ' xmlns:tools="http://schemas.android.com/tools">'
    content = content[:root_match.start()] + updated_root + content[root_match.end():]

permissions = (
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.REQUEST_DISCOVERABLE",
)
for permission in permissions:
    # Restrict whitespace to the current line; \\s would consume indentation
    # from the following XML element and make repeated runs non-idempotent.
    pattern = re.compile(
        r'(?m)^[ \\t]*<uses-permission\\b(?=[^>]*android:name="'
        + re.escape(permission)
        + r'")[^>]*/>[ \\t]*(?:\\r?\\n|$)'
    )
    content = pattern.sub("", content)

connect = '    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />'
if connect not in content:
    raise SystemExit("BLUETOOTH_CONNECT permission declaration not found")

remove_lines = [
    f'    <uses-permission android:name="{permission}" tools:node="remove" />'
    for permission in permissions
]
for line in remove_lines:
    if line not in content:
        content = content.replace(connect, connect + "\\n" + line, 1)
if any(content.count(line) != 1 for line in remove_lines):
    raise SystemExit("Unused Bluetooth permission removal markers are missing or duplicated")

# Parse the proposed XML before replacing the original file.
ET.fromstring(content)
atomic_write_text(MANIFEST, content)
ET.parse(MANIFEST)

# The preceding source patch records a hash for every modified file. This
# final least-privilege pass changes the manifest again, so refresh that one
# entry before the preflight compares the report with the final source tree.
if REPORT.exists():
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read TorqScan patch report: {exc}") from exc
    if not isinstance(report, dict):
        raise SystemExit("TorqScan patch report root must be a JSON object")
    files = report.get("files")
    relative_manifest = "android/app/src/main/AndroidManifest.xml"
    if not isinstance(files, dict) or relative_manifest not in files:
        raise SystemExit("TorqScan patch report has no Android manifest hash to refresh")
    files[relative_manifest] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    atomic_write_text(REPORT, json.dumps(report, indent=2) + "\\n")

print("Verified paired-device-only manifest: CONNECT retained; SCAN, location and discoverability removed")
