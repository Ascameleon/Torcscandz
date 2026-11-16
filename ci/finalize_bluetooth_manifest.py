#!/usr/bin/env python3
"""Enforce least-privilege permissions after every other source patch has run."""
from __future__ import annotations

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
    raise SystemExit("Bluetooth scan/location removal markers are missing or duplicated")

MANIFEST.write_text(content, encoding="utf-8")
ET.parse(MANIFEST)
print("Verified paired-device-only manifest: CONNECT retained; SCAN and location removed")
