import 'package:flutter_test/flutter_test.dart';
import 'package:torqscan/services/connection_endpoint.dart';

void main() {
  group('ConnectionEndpoint', () {
    test('trims valid IPv4 adapter addresses', () {
      final endpoint = ConnectionEndpoint.parse(' 192.168.0.10 ', 35000);
      expect(endpoint.host, '192.168.0.10');
      expect(endpoint.label, '192.168.0.10:35000');
    });

    test('accepts DNS hostnames for configurable adapters', () {
      expect(ConnectionEndpoint.parse('obd-adapter.local', 35000).host, 'obd-adapter.local');
    });

    test('accepts fully-qualified DNS hostnames with a trailing root dot', () {
      final endpoint = ConnectionEndpoint.parse('obd-adapter.local.', 35000);
      expect(endpoint.host, 'obd-adapter.local.');
      expect(endpoint.label, 'obd-adapter.local.:35000');
    });

    test('rejects empty labels before a trailing root dot', () {
      for (final host in ['obd..local.', '.local.', 'obd-adapter..']) {
        expect(() => ConnectionEndpoint.parse(host, 35000), throwsFormatException, reason: host);
      }
    });

    test('accepts IPv6 and formats the endpoint unambiguously', () {
      final endpoint = ConnectionEndpoint.parse('[::1]', 35000);
      expect(endpoint.host, '::1');
      expect(endpoint.label, '[::1]:35000');
    });

    test('rejects bracketed DNS names and mismatched IPv6 brackets', () {
      for (final host in ['[obd-adapter.local]', '[::1', '::1]', '[]']) {
        expect(() => ConnectionEndpoint.parse(host, 35000), throwsFormatException, reason: host);
      }
    });

    test('rejects URL schemes, paths and malformed hostnames', () {
      for (final host in ['http://192.168.0.10', '192.168.0.10/path', '192.168.0.999', 'bad host', '-invalid.local', '']) {
        expect(() => ConnectionEndpoint.parse(host, 35000), throwsFormatException, reason: host);
      }
    });

    test('rejects ports outside the TCP range', () {
      expect(() => ConnectionEndpoint.parse('192.168.0.10', 0), throwsFormatException);
      expect(() => ConnectionEndpoint.parse('192.168.0.10', 65536), throwsFormatException);
    });
  });
}
