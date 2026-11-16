#!/usr/bin/env python3
"""Regression tests for the final Android paired-device permission manifest."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).with_name("finalize_bluetooth_manifest.py")
ANDROID = "{http://schemas.android.com/apk/res/android}"
TOOLS = "{http://schemas.android.com/tools}"
REMOVED = (
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.REQUEST_DISCOVERABLE",
)


def run_finalizer(project: Path) -> None:
    subprocess.run([sys.executable, str(SCRIPT), str(project)], check=True, capture_output=True, text=True)


def test_removes_unused_bluetooth_discovery_permissions_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        project = Path(temporary)
        manifest = project / "android/app/src/main/AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
</manifest>
""",
            encoding="utf-8",
        )

        run_finalizer(project)
        first = manifest.read_text(encoding="utf-8")
        run_finalizer(project)
        second = manifest.read_text(encoding="utf-8")
        assert first == second, "manifest finalization must be idempotent"
        assert all(
            line.startswith("    <uses-permission ") or not line.lstrip().startswith("<uses-permission ")
            for line in first.splitlines()
        ), "manifest permission elements must preserve consistent indentation"

        root = ET.parse(manifest).getroot()
        assert root.tag == "manifest"
        assert "http://schemas.android.com/tools" in root.attrib.values() or "xmlns:tools=" in second
        nodes = root.findall("uses-permission")
        names = [node.get(ANDROID + "name") for node in nodes]
        assert "android.permission.BLUETOOTH_CONNECT" in names
        assert "android.permission.INTERNET" in names
        for permission in REMOVED:
            matches = [node for node in nodes if node.get(ANDROID + "name") == permission]
            assert len(matches) == 1, f"expected one removal marker for {permission}"
            assert matches[0].get(TOOLS + "node") == "remove"
        assert all(
            node.get(ANDROID + "name") not in REMOVED
            or node.get(TOOLS + "node") == "remove"
            for node in nodes
        )


if __name__ == "__main__":
    test_removes_unused_bluetooth_discovery_permissions_and_is_idempotent()
    print("PASS: Android manifest finalizer removes unused discovery/discoverability permissions and is idempotent")
