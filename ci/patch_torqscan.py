#!/usr/bin/env python3
"""Apply the verified compile/runtime fixes to the TorqScan Flutter source archive."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
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
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
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
        child: LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 360;
            final imageWidth =
                (constraints.maxWidth * 0.34).clamp(84.0, 124.0).toDouble();
            return SizedBox(
              height: compact ? 166 : 154,
              child: Row(
                children: [
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            tr(context, 'selected_vehicle'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '${vehicle.brand} ${vehicle.model}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: compact ? 18 : 20,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 5),
                          Text(
                            '${vehicle.year} • ${vehicle.body}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 10),
                          Text(
                            tr(context, 'change'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  SizedBox(
                    width: imageWidth,
                    height: compact ? 166 : 154,
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
            );
          },
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
        title: Text(
          name,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          device.address,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
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


# Apply Torque ScanDZ identity, light default theme and responsive dashboard fixes.
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
settings_text = settings_text.replace("ThemeMode themeMode = ThemeMode.dark;", "ThemeMode themeMode = ThemeMode.light;")
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
manifest_text = manifest_text.replace('android:icon="@drawable/ic_launcher_foreground"', 'android:icon="@mipmap/ic_launcher"')
manifest_text = manifest_text.replace('android:roundIcon="@drawable/ic_launcher_foreground"', 'android:roundIcon="@mipmap/ic_launcher_round"')
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
if "ThemeMode.light" not in settings_text:
    raise RuntimeError("Light theme is not the default.")
if "Dz Torqscan" in main_file.read_text() or "Dz Torqscan" in settings_text:
    raise RuntimeError("Legacy product name remains in app identity files.")

# Format only the modified Dart files when the SDK is available.
if __import__('shutil').which('dart'):
    subprocess.run(
        ["dart", "format", str(home), str(vehicle_info), str(bluetooth)],
        check=True,
        cwd=project,
    )


# Apply the expanded manufacturer/model/generation selector and an explicit scan-first home.
# Keep the original launcher artwork; only the application label is changed.
catalog_payload = "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"
catalog_files = json.loads(zlib.decompress(base64.b64decode(catalog_payload)).decode("utf-8"))
for relative_path, source_text in catalog_files.items():
    target = project / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source_text)
    changes.append(str(target.relative_to(project)))

test_file = project / "test" / "vehicle_catalog_test.dart"
test_file.parent.mkdir(parents=True, exist_ok=True)
test_file.write_text("""import 'package:flutter_test/flutter_test.dart';
import 'package:torqscan/models/vehicle.dart';

void main() {
  test('Dacia and Peugeot ranges include the requested models', () {
    final dacia = VehicleCatalog.modelsForBrand('Dacia').map((v) => v.model).toSet();
    final peugeot = VehicleCatalog.modelsForBrand('Peugeot').map((v) => v.model).toSet();
    expect(dacia, containsAll(['Sandero', 'Sandero Stepway', 'Duster', 'Logan', 'Jogger', 'Lodgy', 'Dokker', 'Spring']));
    expect(peugeot, containsAll(['106', '206', '207', '208', '301', '307', '308', '406', '407', '508', '2008', '3008', '5008', 'Partner']));
  });
  test('vehicle profile identifiers are unique', () {
    final ids = VehicleCatalog.vehicles.map((v) => v.id).toList();
    expect(ids.toSet().length, ids.length);
    expect(VehicleCatalog.vehicles.every((v) => v.engine.trim().isNotEmpty), isTrue);
  });
  test('generic OBD-II/EOBD fallback is available', () {
    expect(VehicleCatalog.byId('generic_obd'), isNotNull);
  });
}
""")
changes.append(str(test_file.relative_to(project)))

if __import__('shutil').which('dart'):
    subprocess.run(
        ["dart", "format", str(project / "lib/models/vehicle.dart"),
         str(project / "lib/screens/home_screen.dart")],
        check=True,
        cwd=project,
    )



# Responsive layout corrections: prevent long labels, values and icons from
# overflowing dashboard cards on narrow phones or enlarged Android text.
dashboard_file = project / "lib/screens/dashboard_screen.dart"
dashboard_text = dashboard_file.read_text()
dashboard_text = dashboard_text.replace(
    """                Text(title, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
""",
    """                Expanded(
                  child: Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    softWrap: false,
                    style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                  ),
                ),
""",
)
dashboard_text = dashboard_text.replace(
    """            Text(
              value,
              style: TextStyle(fontSize: 36, fontWeight: FontWeight.w800, color: accent, height: 1),
            ),
""",
    """            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  value,
                  maxLines: 1,
                  style: TextStyle(fontSize: 36, fontWeight: FontWeight.w800, color: accent, height: 1),
                ),
              ),
            ),
""",
)
dashboard_text = dashboard_text.replace(
    """            Text(unit, style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
""",
    """            Text(
              unit,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
""",
)
dashboard_text = dashboard_text.replace(
    """                  childAspectRatio: 1.35,
""",
    """                  childAspectRatio: 1.12,
""",
)
dashboard_text = dashboard_text.replace(
    """            Text(
              data?.displayValue ?? '—',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: accent),
            ),
""",
    """            Flexible(
              child: Align(
                alignment: Alignment.centerLeft,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(
                    data?.displayValue ?? '—',
                    maxLines: 1,
                    style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: accent),
                  ),
                ),
              ),
            ),
""",
)
dashboard_text = dashboard_text.replace(
    """            Text(
              data?.unit ?? PIDDefinitions.getUnit(pid),
              style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
""",
    """            Text(
              data?.unit ?? PIDDefinitions.getUnit(pid),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
""",
)
dashboard_file.write_text(dashboard_text)
changes.append(str(dashboard_file.relative_to(project)))

# Preserve Android's native text scaling; responsive widgets must handle it.
main_file = project / "lib/main.dart"
main_text = main_file.read_text()
old_builder = """        builder: (context, child) => Directionality(
          textDirection: settings.isArabic ? TextDirection.rtl : TextDirection.ltr,
          child: child!,
        ),
"""
new_builder = old_builder
if old_builder not in main_text:
    raise RuntimeError("Expected MaterialApp builder was not found for responsive text scaling")
main_file.write_text(main_text.replace(old_builder, new_builder))
changes.append(str(main_file.relative_to(project)))

# Adapt the vehicle selector to compact phones and prevent long model labels
# from forcing grid cards or their action controls outside the viewport.
selector_file = project / "lib/screens/vehicle_selector_screen.dart"
selector_text = selector_file.read_text()
# Locate the GridView and its enclosing Expanded widget without assuming
# that Dart's formatter preserves a particular whitespace layout.
grid_match = re.search(r"GridView\s*\.\s*builder\s*\(", selector_text)
if grid_match is None:
    raise RuntimeError("Vehicle selector GridView.builder widget was not found")
expanded_matches = list(
   # Adapt the actual three-step vehicle selector (ListView, not a vehicle grid)
# so brand chips, model names, generation details and action labels stay bounded.
selector_file = project / "lib/screens/vehicle_selector_screen.dart"
selector_text = selector_file.read_text()

selector_text = replace_between(
    selector_text,
    "          Wrap(\n",
    "          const SizedBox(height: 22),",
    """          LayoutBuilder(
            builder: (context, constraints) {
              final compact = constraints.maxWidth < 420;
              final chipWidth = compact
                  ? (constraints.maxWidth - 8) / 2
                  : (constraints.maxWidth - 16) / 3;
              return Wrap(
                spacing: 8,
                runSpacing: 8,
                children: brands.map((brand) => ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: chipWidth),
                  child: ChoiceChip(
                    label: Text(
                      brand,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    selected: _brand == brand,
                    onSelected: (_) => setState(() {
                      _brand = brand;
                      _model = null;
                      _selected = null;
                    }),
                  ),
                )).toList(),
              );
            },
          ),
""",
    "vehicle_selector.brand_chips",
)

selector_text, model_count = re.subn(
    r"DropdownMenuItem\(value: model,\s*child: Text\(model\)\)",
    """DropdownMenuItem(
              value: model,
              child: Text(
                model,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            )""",
    selector_text,
    count=1,
)
selector_text, generation_count = re.subn(
    r"title:\s*Text\(profile\.generation,\s*style:\s*const TextStyle\(fontWeight:\s*FontWeight\.w700\)\)",
    """title: Text(
                    profile.generation,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  )""",
    selector_text,
    count=1,
    flags=re.S,
)
selector_text, details_count = re.subn(
    r"child:\s*Text\('\$\{profile\.year\}\\n\$\{profile\.engine\}\\n\$\{profile\.body\}'\)",
    """child: Text(
                      profile.year + '\\n' + profile.engine + '\\n' + profile.body,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    )""",
    selector_text,
    count=1,
)
if model_count != 1 or generation_count != 1 or details_count != 1:
    raise RuntimeError(
        "Responsive selector text guards missing: "
        f"model={model_count}, generation={generation_count}, details={details_count}"
    )

selector_text = selector_text.replace(
    "                  isThreeLine: true,",
    """                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  visualDensity: VisualDensity.compact,
                  dense: true,
                  isThreeLine: true,""",
    1,
)
selector_text = selector_text.replace(
    "            label: const Text('Je ne trouve pas mon véhicule — OBD-II / EOBD'),",
    """            label: const Flexible(
              child: Text(
                'Je ne trouve pas mon véhicule — OBD-II / EOBD',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),""",
    1,
)
selector_text = selector_text.replace(
    "            label: const Text('Valider ce véhicule'),",
    """            label: const Flexible(
              child: Text(
                'Valider ce véhicule',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),""",
    1,
)
selector_file.write_text(selector_text)
changes.append(str(selector_file.relative_to(project)))

responsive_test = project / "test" / "responsive_vehicle_selector_test.dart"
responsive_test.write_text("""import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:torqscan/core/app_settings.dart';
import 'package:torqscan/screens/vehicle_selector_screen.dart';

Future<AppSettings> pumpSelector(
  WidgetTester tester, {
  required Size size,
  required String language,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  final settings = AppSettings()..language = language;

  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: settings,
      child: MaterialApp(
        home: const VehicleSelectorScreen(),
        builder: (context, child) {
          final media = MediaQuery.of(context);
          return MediaQuery(
            data: media.copyWith(textScaler: TextScaler.linear(1.3)),
            child: Directionality(
              textDirection:
                  language == 'ar' ? TextDirection.rtl : TextDirection.ltr,
              child: child!,
            ),
          );
        },
      ),
    ),
  );
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
  return settings;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('320px French selector completes manufacturer/model/profile selection without overflow', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final settings = await pumpSelector(
      tester,
      size: const Size(320, 720),
      language: 'fr',
    );

    expect(find.byType(ListView), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Mercedes');
    await tester.pumpAndSettle();
    expect(find.text('Mercedes-Benz'), findsOneWidget);

    await tester.tap(find.text('Mercedes-Benz'));
    await tester.pumpAndSettle();
    final modelField = find.byType(DropdownButtonFormField<String>);
    await tester.ensureVisible(modelField);
    await tester.tap(modelField);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Classe C').last);
    await tester.pumpAndSettle();

    final profileTile = find.byType(RadioListTile<String>);
    await tester.ensureVisible(profileTile);
    expect(find.text('W203–W206'), findsOneWidget);
    await tester.tap(profileTile);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Valider ce véhicule'));
    await tester.pump();
    expect(settings.selectedVehicleId, 'mercedes_c');
    expect(tester.takeException(), isNull);
  });

  testWidgets('360px RTL selector remains scrollable with reachable actions', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await pumpSelector(
      tester,
      size: const Size(360, 780),
      language: 'ar',
    );

    final list = find.byType(ListView);
    expect(list, findsOneWidget);
    expect(Directionality.of(tester.element(list)), TextDirection.rtl);
    await tester.drag(list, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(find.text('Valider ce véhicule'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
""")
changes.append(str(responsive_test.relative_to(project)))

if __import__('shutil').which('dart'):
    subprocess.run(
        ["dart", "format", str(selector_file), str(responsive_test)],
        check=True,
        cwd=project,
    )

json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": "patched", "files": changes, "report": report}, indent=2))
