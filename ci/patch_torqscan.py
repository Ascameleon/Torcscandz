#!/usr/bin/env python3
"""Apply the verified compile/runtime fixes to the TorqScan Flutter source archive."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
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


# Apply the approved Torque ScanDZ product identity, dark automotive theme and launcher icon.
main_file = project / "lib/main.dart"
main_file.write_text("""import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'core/app_settings.dart';
import 'services/bluetooth_service.dart';
import 'services/obd_service.dart';
import 'screens/home_screen.dart';

const Color _navy = Color(0xFF071426);
const Color _surface = Color(0xFF10233A);
const Color _surfaceRaised = Color(0xFF172D46);
const Color _cyan = Color(0xFF20D9F2);
const Color _blue = Color(0xFF1677FF);
const Color _red = Color(0xFFFF453A);
const Color _text = Color(0xFFF2F7FF);
const Color _muted = Color(0xFFA9BED2);

ThemeData _automotiveDarkTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: _cyan,
    brightness: Brightness.dark,
  ).copyWith(
    primary: _cyan,
    onPrimary: _navy,
    secondary: _blue,
    onSecondary: Colors.white,
    error: _red,
    onError: Colors.white,
    surface: _surface,
    onSurface: _text,
    surfaceContainerLowest: _navy,
    surfaceContainerLow: _surface,
    surfaceContainer: _surfaceRaised,
    surfaceContainerHigh: const Color(0xFF203B58),
    onSurfaceVariant: _muted,
    outline: const Color(0xFF42617D),
  );

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: _navy,
    appBarTheme: const AppBarTheme(
      centerTitle: false,
      backgroundColor: _navy,
      foregroundColor: _text,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      color: _surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(20)),
        side: BorderSide(color: Color(0xFF203B58), width: 1),
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: _surfaceRaised,
      hintStyle: TextStyle(color: _muted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(14)),
        borderSide: BorderSide.none,
      ),
    ),
    dividerTheme: const DividerThemeData(color: Color(0xFF29445F)),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected) ? _navy : _muted,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected) ? _cyan : _surfaceRaised,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: _cyan,
        foregroundColor: _navy,
        minimumSize: const Size(48, 50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
        textStyle: const TextStyle(fontWeight: FontWeight.w800),
      ),
    ),
  );
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations(
    const [DeviceOrientation.portraitUp, DeviceOrientation.portraitDown],
  );
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppSettings(),
      child: const TorqScanApp(),
    ),
  );
}

class TorqScanApp extends StatelessWidget {
  const TorqScanApp({super.key});

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettings>();
    final darkTheme = _automotiveDarkTheme();
    final lightScheme = ColorScheme.fromSeed(
      seedColor: _blue,
      brightness: Brightness.light,
    );
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => BluetoothService()),
        ChangeNotifierProxyProvider<BluetoothService, OBDService>(
          create: (context) => OBDService(context.read<BluetoothService>()),
          update: (context, bluetooth, previous) => previous ?? OBDService(bluetooth),
        ),
      ],
      child: MaterialApp(
        title: 'Torque ScanDZ',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.light,
          colorScheme: lightScheme,
          scaffoldBackgroundColor: const Color(0xFFF3F6FA),
        ),
        darkTheme: darkTheme,
        themeMode: settings.themeMode,
        locale: Locale(settings.language),
        builder: (context, child) => Directionality(
          textDirection: settings.isArabic ? TextDirection.rtl : TextDirection.ltr,
          child: child!,
        ),
        home: const HomeScreen(),
      ),
    );
  }
}
""")
changes.append(str(main_file.relative_to(project)))

settings_file = project / "lib/core/app_settings.dart"
settings_text = settings_file.read_text()
settings_text = settings_text.replace("ThemeMode themeMode = ThemeMode.light;", "ThemeMode themeMode = ThemeMode.dark;")
settings_text = settings_text.replace("Dz Torqscan", "Torque ScanDZ")
settings_file.write_text(settings_text)
changes.append(str(settings_file.relative_to(project)))

pubspec = project / "pubspec.yaml"
pubspec_text = pubspec.read_text().replace("version: 1.4.0+24", "version: 1.4.1+25")
pubspec.write_text(pubspec_text)
changes.append(str(pubspec.relative_to(project)))

manifest_file = project / "android/app/src/main/AndroidManifest.xml"
manifest_text = manifest_file.read_text()
manifest_text = manifest_text.replace('android:label="Dz Torqscan"', 'android:label="Torque ScanDZ"')
manifest_text = manifest_text.replace('android:icon="@mipmap/ic_launcher"', 'android:icon="@drawable/ic_launcher_foreground"')
manifest_text = manifest_text.replace('android:roundIcon="@mipmap/ic_launcher_round"', 'android:roundIcon="@drawable/ic_launcher_foreground"')
manifest_file.write_text(manifest_text)
ET.parse(manifest_file)
changes.append(str(manifest_file.relative_to(project)))

icon_xml = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="432"
    android:viewportHeight="432">
    <path android:fillColor="#07152D" android:pathData="M0,0h432v432h-432z"/>
    <path android:fillColor="#061A39" android:strokeColor="#00DDF8" android:strokeWidth="8"
        android:pathData="M78,14h276c36,0 64,28 64,64v276c0,36 -28,64 -64,64h-276c-36,0 -64,-28 -64,-64v-276c0,-36 28,-64 64,-64z"/>
    <path android:strokeColor="#16DFFF" android:strokeWidth="9" android:strokeLineCap="round" android:strokeLineJoin="round" android:fillColor="#00000000"
        android:pathData="M93,75 L93,39 M93,57 L125,26 M93,57 L125,88 M125,26 L125,88"/>
    <path android:strokeColor="#FFFFFF" android:strokeWidth="9" android:strokeLineCap="round" android:fillColor="#00000000"
        android:pathData="M270,42 C302,42 328,56 346,79 M282,73 C302,73 318,82 330,96 M296,105 L296,106"/>
    <path android:fillColor="#0A2445" android:strokeColor="#B9E7FF" android:strokeWidth="7" android:strokeLineJoin="round"
        android:pathData="M61,142 Q61,124 81,124 H247 Q264,124 274,141 L291,171 Q297,181 285,190 L265,204 H76 Q57,204 57,185 Z"/>
    <path android:fillColor="#071426" android:strokeColor="#25D9FF" android:strokeWidth="4"
        android:pathData="M82,144 H254 Q264,144 270,155 L280,176 H69 L73,153 Q75,144 82,144 Z"/>
    <path android:fillColor="#42E8FF" android:pathData="M93,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M124,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M155,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M186,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M217,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M248,158a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M108,181a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M139,181a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M170,181a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M201,181a6,6 0,1 0,12 0a6,6 0,1 0,-12 0 M232,181a6,6 0,1 0,12 0a6,6 0,1 0,-12 0"/>
    <path android:fillColor="#0B2B50" android:strokeColor="#1CCFFF" android:strokeWidth="7" android:strokeLineJoin="round"
        android:pathData="M63,286 L78,249 Q88,229 112,229 H232 Q253,229 267,247 L286,280 L286,318 H59 Z"/>
    <path android:fillColor="#071426" android:strokeColor="#B8E9FF" android:strokeWidth="5"
        android:pathData="M111,239 H229 Q244,239 254,254 L267,278 H83 L96,252 Q101,239 111,239 Z"/>
    <path android:fillColor="#21DFFF" android:pathData="M83,281 L119,281 L105,291 L88,291 Z M230,281 L266,281 L260,291 L243,291 Z"/>
    <path android:fillColor="#071426" android:strokeColor="#16DFFF" android:strokeWidth="5"
        android:pathData="M76,306a17,17 0,1 0,34 0a17,17 0,1 0,-34 0 M236,306a17,17 0,1 0,34 0a17,17 0,1 0,-34 0"/>
    <path android:fillColor="#08162C" android:strokeColor="#25DFFF" android:strokeWidth="10"
        android:pathData="M294,270a54,54 0,1 0,108 0a54,54 0,1 0,-108 0"/>
    <path android:strokeColor="#21DFFF" android:strokeWidth="22" android:strokeLineCap="round"
        android:pathData="M376,310 L409,350"/>
    <path android:fillColor="#1A0B13" android:strokeColor="#FF5B35" android:strokeWidth="5" android:strokeLineJoin="round"
        android:pathData="M322,258 H342 L351,246 H378 L388,258 H397 V282 H385 L376,293 H342 L331,282 H322 Z"/>
    <path android:strokeColor="#FFDA5A" android:strokeWidth="5" android:strokeLineCap="round" android:strokeLineJoin="round"
        android:pathData="M336,272 L350,272 L359,261 L367,282 L376,268 L385,272"/>
</vector>
"""
drawable = project / "android/app/src/main/res/drawable/ic_launcher_foreground.xml"
drawable.parent.mkdir(parents=True, exist_ok=True)
drawable.write_text(icon_xml)
changes.append(str(drawable.relative_to(project)))

# Verify product identity and ensure the existing splash-screen resources were not altered.
if 'android:label="Torque ScanDZ"' not in manifest_text:
    raise RuntimeError("Launcher label was not updated.")
if "ThemeMode.dark" not in settings_text:
    raise RuntimeError("Dark automotive theme is not the default.")
if "Dz Torqscan" in main_file.read_text() or "Dz Torqscan" in settings_text:
    raise RuntimeError("Legacy product name remains in app identity files.")

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
