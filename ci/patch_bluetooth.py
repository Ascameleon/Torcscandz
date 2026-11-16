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
s=s.replace("import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';", "import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';\nimport 'package:bluetooth_spp/bluetooth_spp.dart' as spp;\nimport 'package:permission_handler/permission_handler.dart';")
start=s.index('  Future<bool> requestPermissions() async {')
end=s.index('\n  Future<bool> isBluetoothEnabled()',start)
method="""  Future<bool> requestPermissions() async {
    if (defaultTargetPlatform != TargetPlatform.android) return true;
    try {
      final status = await spp.BluetoothSpp.instance.permissionsStatus();
      if (status.allGranted) return true;
      final requested = <Permission>[
        if (status.sdkInt >= 31) ...[
          Permission.bluetoothConnect,
          Permission.bluetoothScan,
        ] else
          Permission.locationWhenInUse,
      ];
      await requested.request();
      final refreshed = await spp.BluetoothSpp.instance.permissionsStatus();
      if (!refreshed.allGranted) {
        _errorMessage = 'Autorisations Bluetooth manquantes : ${refreshed.missing.join(', ')}';
        _state = BluetoothConnectionState.error;
        notifyListeners();
        return false;
      }
      return true;
    } catch (e) {
      _errorMessage = 'Impossible d’obtenir les autorisations Bluetooth : $e';
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
    connection.output.add(bytes);\n    await connection.output.allSent;
  }

"""
s=s[:write_start]+write_method+s[write_end:]
bt.write_text(s)
manifest=p/'android/app/src/main/AndroidManifest.xml'
m=manifest.read_text()
if 'android.permission.BLUETOOTH_SCAN' not in m:
    m=m.replace('    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />', '    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />\n    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" />')
manifest.write_text(m)
print('Bluetooth permissions, RFCOMM timeout and cleanup patched; compatible permission_handler pinned')
