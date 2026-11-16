#!/usr/bin/env python3
from pathlib import Path
import re, sys
p=Path(sys.argv[1])
pub=p/'pubspec.yaml'
s=pub.read_text()
s2=s.replace('  flutter_bluetooth_serial_plus: ^0.5.6','  flutter_bluetooth_serial_plus: ^0.5.7')
if '  bluetooth_spp:' not in s2:
    s2=s2.replace('  flutter_bluetooth_serial_plus: ^0.5.7','  flutter_bluetooth_serial_plus: ^0.5.7\n  bluetooth_spp: ^0.1.0')
# permission_handler 12 pulls Android 14.1.1, whose Kotlin DSL is incompatible
# with the extracted project's Gradle plugin configuration. Use the 11.x line.
s2=re.sub(r'(?m)^  permission_handler: .*$', '  permission_handler: ^11.3.1', s2)
if '  permission_handler:' not in s2:
    s2=s2.replace('  bluetooth_spp: ^0.1.0','  bluetooth_spp: ^0.1.0\n  permission_handler: ^11.3.1')
if 'flutter_bluetooth_serial_plus: ^0.5.7' not in s2 or 'permission_handler: ^11.3.1' not in s2:
    raise SystemExit('pubspec Bluetooth dependency patch anchor mismatch')
pub.write_text(s2)
bt=p/'lib/services/bluetooth_service.dart'
s=bt.read_text()
s=s.replace('  BluetoothConnection? _connection;', '  spp.SppConnection? _connection;')
required_imports = (
    "import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';",
    "import 'package:bluetooth_spp/bluetooth_spp.dart' as spp;",
    "import 'package:permission_handler/permission_handler.dart';",
    "import 'bluetooth_permission_policy.dart';",
)
import_uris = (
    "package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart",
    "package:bluetooth_spp/bluetooth_spp.dart",
    "package:permission_handler/permission_handler.dart",
    "bluetooth_permission_policy.dart",
)
# Normalize by library URI, not the full import directive: the recovered
# archive may already import the same library with a show/as clause.
for import_uri in import_uris:
    pattern = re.compile(
        r"(?m)^[ \t]*import[ \t]+['\"]" + re.escape(import_uri)
        + r"['\"][^;\r\n]*;[ \t]*(?:\r?\n|$)"
    )
    s = pattern.sub("", s)
first_import = re.search(r"(?m)^import[ \t]+.*?;[ \t]*$", s)
if first_import is None:
    raise SystemExit("Bluetooth service has no import section")
s = s[:first_import.end()] + "\n" + "\n".join(required_imports) + s[first_import.end():]
if any(s.count(import_line) != 1 for import_line in required_imports):
    raise SystemExit("Bluetooth service imports are missing or duplicated")
start=s.index('  Future<bool> requestPermissions() async {')
end=s.index('\n  Future<bool> isBluetoothEnabled()',start)
method="""  Future<bool> requestPermissions() async {
    if (defaultTargetPlatform != TargetPlatform.android) return true;
    try {
      final status = await spp.BluetoothSpp.instance.permissionsStatus();
      if (!requiresBluetoothConnectPermission(status.sdkInt)) return true;
      final permission = await Permission.bluetoothConnect.request();
      if (!permission.isGranted) {
        _errorMessage = 'Autorisation Bluetooth CONNECT manquante.';
        _state = BluetoothConnectionState.error;
        notifyListeners();
        return false;
      }
      return true;
    } catch (e) {
      _errorMessage = 'Impossible d’obtenir l’autorisation Bluetooth CONNECT : $e';
      _state = BluetoothConnectionState.error;
      notifyListeners();
      return false;
    }
  }
"""
s=s[:start]+method+s[end:]
start=s.index('  Future<bool> connect(BluetoothDevice device) async {')
end=s.index('\n  Future<bool> connectWifi(',start)
method="""  Future<bool> connect(BluetoothDevice device) async {
    if (_state == BluetoothConnectionState.connecting) return false;
    final address = device.address.trim().toUpperCase();
    if (!RegExp(r'^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$').hasMatch(address)) {
      _errorMessage = 'Adresse Bluetooth invalide pour ${device.name ?? 'cet appareil'}.';
      _state = BluetoothConnectionState.error;
      notifyListeners();
      return false;
    }
    await disconnect(notify: false);
    _state = BluetoothConnectionState.connecting;
    _connectedDevice = device;
    _errorMessage = null;
    notifyListeners();

    final pendingConnection = spp.BluetoothSpp.instance.connect(
      address,
      timeout: const Duration(seconds: 20),
      insecureFallback: true,
      rfcommChannelFallback: true,
    );
    try {
      final connection = await pendingConnection;
      if (!connection.isConnected) {
        await connection.close();
        throw StateError('Le canal RFCOMM n’est pas resté connecté.');
      }
      _connection = connection;
      _state = BluetoothConnectionState.connected;
      notifyListeners();
      return true;
    } catch (e) {
      pendingConnection.then((lateConnection) async {
        if (!identical(_connection, lateConnection)) {
          try { await lateConnection.close(); } catch (_) {}
        }
      }).catchError((_) {});
      _connection = null;
      _connectedDevice = null;
      _state = BluetoothConnectionState.error;
      _errorMessage = 'Échec de connexion Bluetooth RFCOMM à ${device.name ?? address} ($address) : $e';
      notifyListeners();
      return false;
    }
  }
"""
s=s[:start]+method+s[end:]
write_start=s.index('  Future<void> write(String data) async {')
write_end=s.index('\n  @override\n  void dispose()',write_start)
write_method="""  Future<void> write(String data) async {
    final bytes = Uint8List.fromList(data.codeUnits);
    final socket = _wifiSocket;
    if (socket != null) {
      socket.add(bytes);
      await socket.flush();
      return;
    }
    final connection = _connection;
    if (connection == null || !connection.isConnected) {
      throw StateError('Adaptateur OBD2 non connecté');
    }
    await connection.write(bytes);
  }

"""
s=s[:write_start]+write_method+s[write_end:]
bt.write_text(s)

policy=p/'lib/services/bluetooth_permission_policy.dart'
policy.parent.mkdir(parents=True, exist_ok=True)
policy.write_text("""/// Paired-device SPP access needs BLUETOOTH_CONNECT on Android 12+ only.
/// BLUETOOTH_SCAN is reserved for discovery, which this app does not perform.
bool requiresBluetoothConnectPermission(int sdkInt) => sdkInt >= 31;
""")

policy_test=p/'test/bluetooth_permission_policy_test.dart'
policy_test.parent.mkdir(parents=True, exist_ok=True)
policy_test.write_text("""import 'package:flutter_test/flutter_test.dart';
import 'package:torqscan/services/bluetooth_permission_policy.dart';

void main() {
  group('paired-device Bluetooth permission policy', () {
    test('does not request runtime scan/location permission on Android 11 and earlier', () {
      expect(requiresBluetoothConnectPermission(23), isFalse);
      expect(requiresBluetoothConnectPermission(30), isFalse);
    });

    test('requires only Bluetooth CONNECT on Android 12 and later', () {
      expect(requiresBluetoothConnectPermission(31), isTrue);
      expect(requiresBluetoothConnectPermission(35), isTrue);
    });
  });
}
""")

manifest=p/'android/app/src/main/AndroidManifest.xml'
m=manifest.read_text()
root_match=re.search(r'<manifest\b[^>]*>', m, re.S)
if root_match is None:
    raise SystemExit('Android manifest root element not found')
root_tag=root_match.group(0)
if 'xmlns:tools=' not in root_tag:
    updated_root=root_tag[:-1]+' xmlns:tools="http://schemas.android.com/tools">'
    m=m[:root_match.start()]+updated_root+m[root_match.end():]
# This app connects only to already-paired SPP adapters; it never discovers devices.
# Remove scan/location declarations contributed by plugin manifests.
for permission in (
    'android.permission.BLUETOOTH_SCAN',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION',
):
    pattern = r'(?m)^\s*<uses-permission\b(?=[^>]*android:name="' + re.escape(permission) + r'")[^>]*/>\s*\n?'
    m = re.sub(pattern, '', m)
remove_lines = [
    '    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" tools:node="remove" />',
    '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" tools:node="remove" />',
    '    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" tools:node="remove" />',
]
connect='    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />'
if connect not in m:
    raise SystemExit('BLUETOOTH_CONNECT manifest anchor not found')
for remove_line in remove_lines:
    if remove_line not in m:
        m=m.replace(connect, connect+'\n'+remove_line, 1)
if any(m.count(remove_line) != 1 for remove_line in remove_lines):
    raise SystemExit('Bluetooth scan/location permissions were not removed exactly once')
import xml.etree.ElementTree as ET
ET.fromstring(m)
manifest.write_text(m, encoding='utf-8')
ET.parse(manifest)
print('Bluetooth paired-device least-privilege manifest written and parsed; RFCOMM timeout and cleanup patched; permission policy tests installed')
