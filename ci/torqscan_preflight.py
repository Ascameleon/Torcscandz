#!/usr/bin/env python3
"""Source-only preflight for the patched TorqScan Flutter project."""
from pathlib import Path
from hashlib import sha256
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
errors: list[str] = []

def source(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        errors.append(f"Missing source file: {rel}")
        return ""
    return path.read_text(encoding="utf-8")

manifest = ROOT / "android/app/src/main/AndroidManifest.xml"
try:
    ET.parse(manifest)
except Exception as exc:
    errors.append(f"Android manifest XML invalid: {exc}")
manifest_text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""

pubspec = source("pubspec.yaml")
try:
    import yaml
    data = yaml.safe_load(pubspec)
    if data.get("name") != "torqscan" or "flutter" not in data.get("dependencies", {}):
        errors.append("pubspec.yaml project identity/dependencies are invalid")
except ImportError:
    print("WARN: PyYAML unavailable; Flutter CI performs pubspec validation")
except Exception as exc:
    errors.append(f"pubspec.yaml invalid: {exc}")

required = [
    "lib/services/obd_protocol.dart", "lib/services/obd_service.dart",
    "lib/services/bluetooth_service.dart", "lib/services/connection_endpoint.dart",
    "lib/services/bluetooth_permission_policy.dart", "lib/screens/home_screen.dart",
    "lib/screens/dtc_screen.dart", "test/obd_protocol_test.dart",
    "test/connection_endpoint_test.dart", "test/bluetooth_permission_policy_test.dart",
    "torqscan-patch-report.json",
]
for rel in required:
    source(rel)

assets = ROOT / "assets/vehicles"
for name in ["peugeot_208.png", "renault_clio.png", "dacia_sandero.png", "vw_golf.png", "toyota_corolla.png", "mercedes_c.png", "hyundai_tucson.png", "generic_obd.png"]:
    if not (assets / name).is_file():
        errors.append(f"Missing vehicle asset: {name}")

protocol = source("lib/services/obd_protocol.dart")
protocol_tests = source("test/obd_protocol_test.dart")
for token in ["toRadixString(16)", "positiveService", "static bool isFailure(String response)"]:
    if token not in protocol:
        errors.append(f"OBD protocol safeguard missing: {token}")
for token in ["response.split(RegExp(r'[\\r\\n]+'))", "for (final line in response.split(RegExp(r'[\\r\\n]+')))"]:
    if token not in protocol:
        errors.append(f"OBD parser no longer preserves ECU response line boundaries: {token}")
for token in ["matches positive service", "decode RPM", "decode DTC", "decodes supported PID blocks", "multiple ECU response lines without merging frames", "deduplicates repeated DTCs across ECU response lines", "keeps valid ECU DTCs when another ECU returns NO DATA", "does not merge PID payload across ECU response lines", "distinguishes empty DTC response from adapter failure", "unions supported PIDs reported by multiple ECUs"]:
    if token not in protocol_tests:
        errors.append(f"Missing protocol regression test: {token}")

obd_service = source("lib/services/obd_service.dart")
for token in ["_bluetooth.markTransportEnded(reason: _lastError, failed: true)", "_bluetooth.markTransportEnded(reason: _lastError)", "_completeResponse('DISCONNECTED')", "_protocol = null;"]:
    if token not in obd_service:
        errors.append(f"Missing OBD stream/disconnect recovery: {token}")

transport = source("lib/services/bluetooth_service.dart")
for import_line in (
    "import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';",
    "import 'package:bluetooth_spp/bluetooth_spp.dart' as spp;",
    "import 'package:permission_handler/permission_handler.dart';",
    "import 'bluetooth_permission_policy.dart';",
):
    if transport.count(import_line) != 1:
        errors.append(f"Bluetooth service import must occur exactly once: {import_line}")
if "void markTransportEnded({String? reason, bool failed = false})" not in transport:
    errors.append("Transport EOF/error state synchronizer missing")
if not re.search(r"_state\s*=\s*failed\s*\?\s*BluetoothConnectionState\.error\s*:\s*BluetoothConnectionState\.disconnected", transport):
    errors.append("Transport terminal state must distinguish error from remote disconnect")
if not re.search(r"socket\?\.destroy\(\)", transport):
    errors.append("Wi-Fi socket is not destroyed on terminal transport state")
if not re.search(r"Socket\.connect\(\s*normalizedHost\s*,\s*port", transport):
    errors.append("Wi-Fi TCP connect call missing")
for token in ["socket.add(bytes)", "Stream<Uint8List>? get inputStream", "ConnectionEndpoint.parse(host, port)"]:
    if token not in transport:
        errors.append(f"Wi-Fi transport safeguard missing: {token}")

home = source("lib/screens/home_screen.dart")
if r"\${tr(context, 'wifi_connect_failed')}" in home:
    errors.append("Wi-Fi error interpolation is escaped and breaks Dart string quoting")
if 'Text("${tr(context, \'wifi_connect_failed\')}: $error")' not in home:
    errors.append("Wi-Fi failure message is not safely localized")
for key in ["connection_mode", "wifi_host", "wifi_port", "connect_wifi", "wifi_hint", "wifi_invalid", "wifi_connect_failed"]:
    if f"tr(context, '{key}')" not in home:
        errors.append(f"Wi-Fi UI is not localized through {key}")
if not re.search(r"connectWifi\(\s*host\s*,\s*port\s*,?\s*\)", home):
    errors.append("Wi-Fi UI no longer calls the validated connectWifi(host, port) method")

settings = source("lib/core/app_settings.dart")
for lang in ["fr", "en", "ar"]:
    section_start = settings.find(f"    '{lang}': {{")
    section_end = settings.find("\n    },", section_start)
    section = settings[section_start:section_end] if section_start >= 0 and section_end >= 0 else ""
    for key in ["wifi_host", "wifi_port", "connect_wifi", "wifi_hint", "wifi_invalid", "wifi_connect_failed", "dtc_scan_disabled", "dtc_scan_disabled_desc"]:
        if f"'{key}':" not in section:
            errors.append(f"Missing {key} translation for {lang}")

policy = source("lib/services/bluetooth_permission_policy.dart")
policy_test = source("test/bluetooth_permission_policy_test.dart")
if "bool requiresBluetoothConnectPermission(int sdkInt) => sdkInt >= 31;" not in policy:
    errors.append("Paired-device Bluetooth permission policy must request CONNECT only on Android 12+")
for token in ["requiresBluetoothConnectPermission(30)", "requiresBluetoothConnectPermission(31)"]:
    if token not in policy_test:
        errors.append(f"Missing Android Bluetooth permission boundary test: {token}")
permission_section = transport.split("Future<bool> requestPermissions()", 1)[-1].split("Future<bool> isBluetoothEnabled()", 1)[0]
if "Permission.bluetoothConnect.request()" not in permission_section:
    errors.append("Android 12+ Bluetooth CONNECT runtime request missing")
if "Permission.bluetoothScan" in permission_section or "Permission.locationWhenInUse" in permission_section:
    errors.append("Paired-device-only flow requests unused Bluetooth SCAN/location permission")
if "requiresBluetoothConnectPermission(status.sdkInt)" not in permission_section:
    errors.append("Bluetooth permission policy is not applied using the Android SDK level")
if "android.permission.BLUETOOTH_CONNECT" not in manifest_text:
    errors.append("BLUETOOTH_CONNECT manifest permission missing")
manifest_root = ET.parse(manifest).getroot()
android_ns = "{http://schemas.android.com/apk/res/android}"
tools_ns = "{http://schemas.android.com/tools}"
for permission in (
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
):
    nodes = [
        node for tag in ("uses-permission", "uses-permission-sdk-23")
        for node in manifest_root.findall(tag)
        if node.get(android_ns + "name") == permission
    ]
    if len(nodes) != 1 or nodes[0].get(tools_ns + "node") != "remove":
        errors.append(f"Paired-device-only flow must remove unused {permission} from the merged manifest")
if "android.permission.INTERNET" not in manifest_text:
    errors.append("Android INTERNET permission missing for Wi-Fi TCP")
if "android.hardware.bluetooth\" android:required=\"false\"" not in manifest_text:
    errors.append("Bluetooth hardware must remain optional because Wi-Fi is also supported")
for permission in (
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
):
    direct_declarations = [
        node for tag in ("uses-permission", "uses-permission-sdk-23")
        for node in manifest_root.findall(tag)
        if node.get(android_ns + "name") == permission
        and node.get(tools_ns + "node") != "remove"
    ]
    if direct_declarations:
        errors.append(f"App manifest retains a direct {permission} declaration instead of a removal marker")

endpoint = source("lib/services/connection_endpoint.dart")
endpoint_tests = source("test/connection_endpoint_test.dart")
for token in ["InternetAddress.tryParse(host)", "host.contains(':')", "port < 1 || port > 65535", "String get label", "final bracketed = host.startsWith('[') || host.endsWith(']')", "bracketLiteral.type != InternetAddressType.IPv6"]:
    if token not in endpoint:
        errors.append(f"Missing Wi-Fi endpoint validation rule: {token}")
for token in ["trims valid IPv4 adapter addresses", "accepts DNS hostnames", "accepts IPv6", "rejects bracketed DNS names", "rejects URL schemes", "rejects ports outside the TCP range"]:
    if token not in endpoint_tests:
        errors.append(f"Missing Wi-Fi endpoint regression test: {token}")

# DTC scan disabled is not equivalent to a clean ECU; tolerate Dart formatting.
dtc = source("lib/screens/dtc_screen.dart")
if not re.search(r"final\s+dtcScanDisabled\s*=\s*!scanOptions\.confirmedDtc\s*&&\s*!scanOptions\.pendingDtc\s*;", dtc):
    errors.append("DTC screen does not detect when both DTC scans are disabled")
if "tr(context, 'dtc_scan_disabled')" not in dtc:
    errors.append("DTC screen does not show a distinct disabled-scan state")

for icon in [
    "android/app/src/main/res/mipmap-mdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-hdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xhdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml",
    "android/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml",
]:
    if not (ROOT / icon).is_file():
        errors.append(f"Missing launcher icon resource: {icon}")

report_path = ROOT / "torqscan-patch-report.json"
try:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for rel, expected in report.get("files", {}).items():
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"Patch report references missing file: {rel}")
        elif sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"Patch report SHA-256 mismatch: {rel}")
except Exception as exc:
    errors.append(f"Could not verify patch report: {exc}")

if errors:
    print("PREFLIGHT FAILED")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)
print("PREFLIGHT PASSED: source, OBD protocol, Wi-Fi endpoint, DTC state, translated Wi-Fi UI, and least-privilege paired-device Bluetooth permissions.")
print("NOTE: Flutter CI and physical OBD2 testing remain separate validations.")