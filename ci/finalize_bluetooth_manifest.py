#!/usr/bin/env python3
"""Enforce least-privilege permissions after every other source patch has run."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MANIFEST = PROJECT / "android/app/src/main/AndroidManifest.xml"
if not MANIFEST.is_file():
    raise SystemExit(f"Android manifest missing: {MANIFEST}")

content = MANIFEST.read_text(encoding="utf-8")
root_match = re.search(r"<manifest\b[^>]*>", content, re.S)
if root_match is None:
    raise SystemExit("Android manifest root element not found")
root_tag = root_match.group(0)
if not re.search(r"\bxmlns:tools\s*=", root_tag):
    updated_root = root_tag[:-1] + ' xmlns:tools="http://schemas.android.com/tools">'
    content = content[:root_match.start()] + updated_root + content[root_match.end():]

permissions = (
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.REQUEST_DISCOVERABLE",
)
for permission in permissions:
    # Restrict whitespace to the current line; \s would consume indentation
    # from the following XML element and make repeated runs non-idempotent.
    pattern = re.compile(
        r'(?m)^[ \t]*<uses-permission\b(?=[^>]*android:name="'
        + re.escape(permission)
        + r'")[^>]*/>[ \t]*(?:\r?\n|$)'
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
        content = content.replace(connect, connect + "\n" + line, 1)
if any(content.count(line) != 1 for line in remove_lines):
    raise SystemExit("Unused Bluetooth permission removal markers are missing or duplicated")

MANIFEST.write_text(content, encoding="utf-8")
ET.parse(MANIFEST)

# The preceding source patch records a hash for every modified file. This
# final least-privilege pass changes the manifest again, so refresh that one
# entry before the preflight compares the report with the final source tree.
REPORT = PROJECT / "torqscan-patch-report.json"
if REPORT.is_file():
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read TorqScan patch report: {exc}") from exc
    files = report.get("files")
    relative_manifest = "android/app/src/main/AndroidManifest.xml"
    if not isinstance(files, dict) or relative_manifest not in files:
        raise SystemExit("TorqScan patch report has no Android manifest hash to refresh")
    files[relative_manifest] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    REPORT.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")

print("Verified paired-device-only manifest: CONNECT retained; SCAN, location and discoverability removed")
