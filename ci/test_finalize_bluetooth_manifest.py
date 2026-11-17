#!/usr/bin/env python3
"""Regression tests for the final Android paired-device permission manifest."""
from __future__ import annotations

import hashlib
import json
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


def manifest_path(project: Path) -> Path:
    return project / "android/app/src/main/AndroidManifest.xml"


def write_valid_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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


def run_finalizer_result(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(project)],
        check=False,
        capture_output=True,
        text=True,
    )


def run_finalizer(project: Path) -> None:
    result = run_finalizer_result(project)
    assert result.returncode == 0, result.stderr or result.stdout


def test_removes_unused_bluetooth_discovery_permissions_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        project = Path(temporary)
        manifest = manifest_path(project)
        write_valid_manifest(manifest)
        report_path = project / "torqscan-patch-report.json"
        report_path.write_text(
            json.dumps({
                "files": {
                    "android/app/src/main/AndroidManifest.xml":
                        hashlib.sha256(manifest.read_bytes()).hexdigest()
                }
            }),
            encoding="utf-8",
        )

        run_finalizer(project)
        first_report = json.loads(report_path.read_text(encoding="utf-8"))
        expected_manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
        assert first_report["files"]["android/app/src/main/AndroidManifest.xml"] == expected_manifest_hash, (
            "final manifest hash must be refreshed in the patch report"
        )
        first_report_text = report_path.read_text(encoding="utf-8")
        first = manifest.read_text(encoding="utf-8")
        run_finalizer(project)
        second = manifest.read_text(encoding="utf-8")
        assert first == second, "manifest finalization must be idempotent"
        assert report_path.read_text(encoding="utf-8") == first_report_text, (
            "manifest patch-report hash must remain stable on repeated finalization"
        )
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


def assert_symlink_rejected(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 0, "finalizer must reject symlinked project paths"
    assert "symbolic link" in result.stderr.lower(), result.stderr or result.stdout


def test_rejects_symlinked_manifest_without_modifying_target() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = root / "project"
        outside = root / "outside-manifest.xml"
        project.mkdir()
        outside.write_text(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android"/>',
            encoding="utf-8",
        )
        manifest = manifest_path(project)
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(outside)
        before = outside.read_bytes()

        result = run_finalizer_result(project)

        assert_symlink_rejected(result)
        assert outside.read_bytes() == before, "symlink target must remain untouched"


def test_rejects_symlinked_manifest_parent_without_modifying_target() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = root / "project"
        outside_android = root / "outside-android"
        project.mkdir()
        outside_manifest = manifest_path(outside_android)
        write_valid_manifest(outside_manifest)
        android_link = project / "android"
        android_link.symlink_to(outside_android, target_is_directory=True)
        before = outside_manifest.read_bytes()

        result = run_finalizer_result(project)

        assert_symlink_rejected(result)
        assert outside_manifest.read_bytes() == before, "symlinked parent target must remain untouched"


def test_rejects_symlinked_patch_report_before_modifying_manifest() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = root / "project"
        project.mkdir()
        manifest = manifest_path(project)
        write_valid_manifest(manifest)
        outside_report = root / "outside-report.json"
        outside_report.write_text('{"files": {}}', encoding="utf-8")
        report_link = project / "torqscan-patch-report.json"
        report_link.symlink_to(outside_report)
        manifest_before = manifest.read_bytes()
        report_before = outside_report.read_bytes()

        result = run_finalizer_result(project)

        assert_symlink_rejected(result)
        assert manifest.read_bytes() == manifest_before, "manifest must not be changed when report path is unsafe"
        assert outside_report.read_bytes() == report_before, "symlink target report must remain untouched"




def test_rejects_invalid_patch_report_before_modifying_manifest() -> None:
    relative_manifest = "android/app/src/main/AndroidManifest.xml"
    invalid_reports = (
        ("{invalid", "Cannot read TorqScan patch report"),
        (json.dumps({"files": {}}), "no Android manifest hash"),
        (
            json.dumps({"files": {relative_manifest: "not-a-sha256"}}),
            "invalid Android manifest SHA-256",
        ),
    )

    for report_content, expected_error in invalid_reports:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            manifest = manifest_path(project)
            write_valid_manifest(manifest)
            manifest_before = manifest.read_bytes()
            report_path = project / "torqscan-patch-report.json"
            report_path.write_text(report_content, encoding="utf-8")
            report_before = report_path.read_bytes()

            result = run_finalizer_result(project)

            assert result.returncode != 0, "invalid patch report must be rejected"
            assert expected_error in result.stderr, result.stderr or result.stdout
            assert manifest.read_bytes() == manifest_before, (
                "manifest must remain unchanged when the patch report is invalid"
            )
            assert report_path.read_bytes() == report_before, (
                "invalid patch report must remain unchanged"
            )

if __name__ == "__main__":
    test_removes_unused_bluetooth_discovery_permissions_and_is_idempotent()
    test_rejects_symlinked_manifest_without_modifying_target()
    test_rejects_symlinked_manifest_parent_without_modifying_target()
    test_rejects_symlinked_patch_report_before_modifying_manifest()
    test_rejects_invalid_patch_report_before_modifying_manifest()
    print("PASS: manifest permissions are least-privilege, idempotent, and reject symlinked paths")
