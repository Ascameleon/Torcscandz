#!/usr/bin/env python3
"""Apply the verified compile/runtime fixes to the TorqScan Flutter source archive."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_torqscan.py <flutter-project-directory>")

project = Path(sys.argv[1]).resolve()
if not (project / "pubspec.yaml").is_file():
    raise SystemExit(f"Not a Flutter project: {project}")


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:start] + replacement + text[end:]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

changes: list[str] = []

# Repair two malformed widget trees in the dashboard without changing the UI intent.
home = project / "lib/screens/home_screen.dart"
home_text = home.read_text()
vehicle_card = """  Widget _vehicleCard(BuildContext context, VehicleModel? vehicle) {
    final openSelector = () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const VehicleSelectorScreen()),
        );

    if (vehicle == null) {
      return Card(
        child: InkWell(
          onTap: openSelector,
          borderRadius: BorderRadius.circular(18),
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 27,
                  child: Icon(Icons.directions_car_outlined),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        tr(context, 'select_vehicle'),
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        tr(context, 'choose_model'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
          ),
        ),
      );
    }

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: openSelector,
        child: SizedBox(
          height: 150,
          child: Row(
            children: [
              Expanded(
                flex: 5,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        tr(context, 'selected_vehicle'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${vehicle.brand} ${vehicle.model}',
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        '${vehicle.year} • ${vehicle.body}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 10),
                      Text(
                        tr(context, 'change'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.primary,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                flex: 5,
                child: Container(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: Image.asset(
                    vehicle.image,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Icon(
                      Icons.directions_car,
                      size: 64,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

"""
home_text = replace_between(
    home_text,
    "  Widget _vehicleCard(BuildContext context, VehicleModel? vehicle) {",
    "  String _scanSummary(",
    vehicle_card,
    "home_screen._vehicleCard",
)
device_tile = """  Widget _deviceTile(BuildContext context, BluetoothDevice device) {
    final name = device.name ?? 'Bluetooth';
    final isObd = RegExp(
      r'OBD|ELM|V-LINK|VLINK|OBDII|OBD2',
      caseSensitive: false,
    ).hasMatch(name);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
        leading: CircleAvatar(
          backgroundColor: isObd
              ? Theme.of(context).colorScheme.primaryContainer
              : Theme.of(context).colorScheme.surfaceContainerHighest,
          child: Icon(isObd ? Icons.car_repair : Icons.bluetooth),
        ),
        title: Text(name, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(
          device.address,
          style: Theme.of(context).textTheme.bodySmall,
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => _connectToDevice(device),
      ),
    );
  }
"""
home_text = replace_between(
    home_text,
    "  Widget _deviceTile(BuildContext context, BluetoothDevice device) {",
    "\n}",
    device_tile,
    "home_screen._deviceTile",
)
home.write_text(home_text)
changes.append(str(home.relative_to(project)))

# Rebuild the diagnostic screen's widget tree in formatted Dart to restore balanced closures.
vehicle_info = project / "lib/screens/vehicle_info_screen.dart"
vehicle_info_text = """import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_settings.dart';
import '../services/obd_service.dart';

class VehicleInfoScreen extends StatelessWidget {
  const VehicleInfoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'diagnostic'))),
      body: Consumer<OBDService>(
        builder: (context, obd, _) {
          final caps = obd.capabilities;
          final supported = obd.supportedPids.toList()..sort();

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _section(
                context,
                tr(context, 'connection'),
                [
                  _row(context, tr(context, 'protocol'), obd.protocol ?? '—'),
                  _row(context, tr(context, 'obd_standard'), caps.obdStandard ?? '—'),
                  _row(context, tr(context, 'supported_pids'), '${supported.length}'),
                ],
              ),
              const SizedBox(height: 14),
              _section(
                context,
                tr(context, 'system_info'),
                [
                  if (supported.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(tr(context, 'not_detected')),
                    )
                  else
                    Wrap(
                      spacing: 7,
                      runSpacing: 7,
                      children: supported.map((pid) => Chip(label: Text(pid))).toList(),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    tr(context, 'reality'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      height: 1.45,
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _section(BuildContext context, String title, List<Widget> children) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 10),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
          ),
          Flexible(child: Text(value, textAlign: TextAlign.right)),
        ],
      ),
    );
  }
}
"""
vehicle_info.write_text(vehicle_info_text)
changes.append(str(vehicle_info.relative_to(project)))

# Confirm the OBD stream owner reports EOF/errors before relying on the nullable socket state.
obd_service = project / "lib/services/obd_service.dart"
if not obd_service.is_file() or "markTransportEnded" not in obd_service.read_text():
    raise RuntimeError("OBDService does not expose the expected transport-end lifecycle hook")

# Use the Socket API's supported lifecycle: the OBD stream reports EOF/errors and clears the socket.
bluetooth = project / "lib/services/bluetooth_service.dart"
bt = bluetooth.read_text()
bt = bt.replace(
    "bool get isWifiConnected => _state == BluetoothConnectionState.connected && _wifiSocket != null && !_wifiSocket!.destroyed;",
    "bool get isWifiConnected => _state == BluetoothConnectionState.connected && _wifiSocket != null;",
)
bt = bt.replace(
    "bool get isConnected => _state == BluetoothConnectionState.connected && ((_connection?.isConnected ?? false) || (_wifiSocket != null && !_wifiSocket!.destroyed));",
    "bool get isConnected => _state == BluetoothConnectionState.connected &&\n      ((_connection?.isConnected ?? false) || _wifiSocket != null);",
)
bt = bt.replace(
    "    if (socket != null && !socket.destroyed) socket.destroy();",
    "    try { socket?.destroy(); } catch (_) {}",
)
write_method = """  Future<void> write(String data) async {
    final bytes = Uint8List.fromList(data.codeUnits);
    final socket = _wifiSocket;
    if (socket != null) {
      try {
        socket.add(bytes);
        await socket.flush();
        return;
      } catch (error) {
        markTransportEnded(
          reason: 'Connexion Wi-Fi interrompue : $error',
          failed: true,
        );
        rethrow;
      }
    }

    final connection = _connection;
    if (connection == null || !connection.isConnected) {
      throw StateError('Adaptateur OBD2 non connecté');
    }
    connection.output.add(bytes);
    await connection.output.allSent;
  }

"""
bt = replace_between(
    bt,
    "  Future<void> write(String data) async {",
    "  @override\n  void dispose()",
    write_method,
    "bluetooth_service.write",
)
if "destroyed" in bt:
    raise RuntimeError("BluetoothService still references the unsupported Socket.destroyed property")
bluetooth.write_text(bt)
changes.append(str(bluetooth.relative_to(project)))

# Format only the modified Dart files when the SDK is available.
if __import__('shutil').which('dart'):
    subprocess.run(
        ["dart", "format", str(home), str(vehicle_info), str(bluetooth)],
        check=True,
        cwd=project,
    )

report = {
    "patch": "torqscan-dart-compile-fixes-v1",
    "files": {name: sha256(project / name) for name in changes},
    "socket_destroyed_references": 0,
}
(project / "torqscan-patch-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": "patched", "files": changes, "report": report}, indent=2))
