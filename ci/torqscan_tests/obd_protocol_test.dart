import 'package:flutter_test/flutter_test.dart';
import 'package:torqscan/services/obd_protocol.dart';

void main() {
  group('ObdProtocol', () {
    test('matches positive service using hexadecimal bytes', () {
      expect(ObdProtocol.findPidData('41 0C 1A F8', '010C', length: 2), [0x1A, 0xF8]);
      expect(ObdProtocol.findPidData('41 0D 28', '010D', length: 1), [0x28]);
      expect(ObdProtocol.findPidData('NO DATA', '010C'), isEmpty);
    });

    test('does not merge PID payload across ECU response lines', () {
      expect(
        ObdProtocol.findPidData('41 0C 1A F8\r\n41 0C 2B 10', '010C', length: 2),
        [0x1A, 0xF8],
      );
      expect(
        ObdProtocol.findPidData('NO DATA\r\n41 0D 28', '010D', length: 1),
        [0x28],
      );
      expect(
        ObdProtocol.findPidData('41 00\r\n41 00 BE 3E B8 13', '0100'),
        [0xBE, 0x3E, 0xB8, 0x13],
      );
    });

    test('decode RPM', () {
      final bytes = ObdProtocol.findPidData('41 0C 1A F8', '010C', length: 2);
      expect(bytes, [0x1A, 0xF8]);
      expect(((bytes[0] << 8) | bytes[1]) / 4, 1726.0);
    });

    test('decode supported PIDs', () {
      final result = ObdProtocol.decodeSupportedPids('41 00 BE 3E B8 13', 0x0100);
      expect(result.contains('0101'), isTrue);
      expect(result.contains('010C'), isTrue);
      expect(result.contains('010D'), isTrue);
      expect(result.contains('0111'), isTrue);
    });

    test('decode DTC', () {
      expect(ObdProtocol.decodeDtcWord(0x0301), 'P0301');
      expect(ObdProtocol.parseDtc('43 01 33 00 00', 0x03), ['P0133']);
    });

    test('decodes supported PID blocks from positive response', () {
      final pids = ObdProtocol.decodeSupportedPids('41 00 BE 3E B8 13', 0x0100);
      expect(pids, containsAll(['0101', '010C', '010D', '0111']));
      expect(ObdProtocol.decodeSupportedPids('NO DATA', 0x0100), isEmpty);
    });

    test('unions supported PIDs reported by multiple ECUs', () {
      final pids = ObdProtocol.decodeSupportedPids(
        '41 00 80 00 00 00\r\n41 00 00 00 08 00',
        0x0100,
      );
      expect(pids, containsAll(['0101', '0115']));
    });

    test('parses DTCs from multiple ECU response lines without merging frames', () {
      expect(
        ObdProtocol.parseDtc('43 01 33 00 00\r\n43 02 10 00 00', 0x03),
        ['P0133', 'P0210'],
      );
    });

    test('deduplicates repeated DTCs across ECU response lines', () {
      expect(
        ObdProtocol.parseDtc('43 01 33\r\n43 01 33', 0x03),
        ['P0133'],
      );
    });

    test('keeps valid ECU DTCs when another ECU returns NO DATA', () {
      expect(
        ObdProtocol.parseDtc('NO DATA\r\n43 01 33 00 00', 0x03),
        ['P0133'],
      );
      expect(ObdProtocol.parseDtc('NO DATA\r\nSEARCHING...', 0x03), isEmpty);
    });

    test('distinguishes empty DTC response from adapter failure', () {
      expect(ObdProtocol.isNegative('NO DATA'), isTrue);
      expect(ObdProtocol.isFailure('NO DATA'), isFalse);
      expect(ObdProtocol.isFailure('UNABLE TO CONNECT'), isTrue);
      expect(ObdProtocol.isFailure('CAN ERROR'), isTrue);
    });

    test('decodes a valid VIN from Mode 09 PID 02', () {
      String responseFor(String vin) =>
          '49 02 01 ' + vin.codeUnits.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ');
      expect(ObdProtocol.decodeVin(responseFor('1HGCM82633A004352')), '1HGCM82633A004352');
      expect(
        ObdProtocol.decodeVin('NO DATA\r\n' + responseFor('1HGCM82633A004352')),
        '1HGCM82633A004352',
      );
    });

    test('rejects malformed VIN lengths, forbidden characters and unrelated responses', () {
      expect(ObdProtocol.decodeVin('NO DATA'), isNull);
      expect(ObdProtocol.decodeVin('49 03 01 31 48 47 43'), isNull);
      final short = '49 02 01 31 48 47 43 4D';
      expect(ObdProtocol.decodeVin(short), isNull);
      final invalid = '1HGCM82633I004352';
      final invalidResponse = '49 02 01 ' +
          invalid.codeUnits.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ');
      expect(ObdProtocol.decodeVin(invalidResponse), isNull);
    });

    test('decodes a valid VIN from Mode 09 PID 02', () {
      String responseFor(String vin) =>
          '49 02 01 ' + vin.codeUnits.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ');
      expect(ObdProtocol.decodeVin(responseFor('1HGCM82633A004352')), '1HGCM82633A004352');
      expect(
        ObdProtocol.decodeVin('NO DATA\r\n' + responseFor('1HGCM82633A004352')),
        '1HGCM82633A004352',
      );
    });

    test('rejects malformed VIN lengths, forbidden characters and unrelated responses', () {
      expect(ObdProtocol.decodeVin('NO DATA'), isNull);
      expect(ObdProtocol.decodeVin('49 03 01 31 48 47 43'), isNull);
      expect(ObdProtocol.decodeVin('49 02 01 31 48 47 43 4D'), isNull);
      final invalid = '1HGCM82633I004352';
      final invalidResponse = '49 02 01 ' +
          invalid.codeUnits.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ');
      expect(ObdProtocol.decodeVin(invalidResponse), isNull);
    });

    test('negative response', () {
      expect(ObdProtocol.isNegative('NO DATA'), isTrue);
      expect(ObdProtocol.isNegative('UNABLE TO CONNECT'), isTrue);
    });
  });
}
