import importlib.util
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'sma_energy_bridge' / 'main.py'
spec = importlib.util.spec_from_file_location('bridge', FILE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ProtocolTests(unittest.TestCase):
    def test_emeter20_frame(self):
        options = {"meter_serial": 900000001, "power_sign": "export_positive",
                   "swap_counters": True}
        block = [0] * 55
        block[16:18] = [5000, 0xFFFE]
        block[19:22] = [0xFF9C, 250, 0x8000]
        block[41], block[49] = 1000, 2000
        frame = bridge.build_emeter20(options, (100, 12.34, 56.78), block, 1234)
        self.assertEqual(len(frame), 608)
        expected_header = bytes.fromhex("534d4100 0004 02a0 00000001 024c 0010 6069 015d")
        self.assertEqual(frame[:20], expected_header)
        self.assertEqual(struct.unpack_from(">II", frame, 20), (900000001, 1234))
        self.assertEqual(frame[-12:], bytes.fromhex("90000000 02030452 00000000"))
        fields = {}
        cursor = 28
        while cursor < len(frame) - 12:
            channel, index, size, tariff = frame[cursor:cursor + 4]
            self.assertEqual((channel, tariff), (0, 0))
            fields[index, size] = int.from_bytes(frame[cursor + 4:cursor + 4 + size], "big")
            cursor += 4 + size
        self.assertEqual(len(fields), 59)
        self.assertEqual(fields[1, 4], 1000)
        self.assertEqual(fields[1, 8], 44_424_000)
        self.assertEqual(fields[2, 8], 204_408_000)
        self.assertEqual(fields[14, 4], 50_000)
        self.assertEqual(fields[21, 4], 1000)
        self.assertEqual(fields[42, 4], 2500)
        self.assertEqual(fields[61, 4], 0)
        self.assertEqual(fields[21, 8], 3_600_000)
        self.assertEqual(fields[22, 8], 7_200_000)

    def test_check_never_creates_multicast_socket(self):
        options = dict(power_sign="export_positive", poll_interval_seconds=5,
                       transmit_interval_seconds=1, stale_after_seconds=15,
                       max_abs_power_w=30000, modbus_unit_id=1,
                       meter_serial=900000001, susy_id=270, meter_model_base=40188,
                       transmit_enabled=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps(options), encoding="utf-8")
            with (patch("sys.argv", ["main.py", "--options", str(path), "--check"]),
                  patch.object(bridge, "fetch_meter", return_value=(10, 20, 30)),
                  patch.object(bridge.socket, "socket") as udp,
                  patch("builtins.print") as output):
                bridge.main()

        udp.assert_not_called()
        self.assertEqual(json.loads(output.call_args.args[0]), {
            "grid_power_w": 10, "import_kwh": 20, "export_kwh": 30,
            "speedwire_bytes": 72,
        })

    def test_import(self):
        frame = bridge.build_frame(900000001, 270, 1200, 12.345, 67.89, 1234)
        # Tag 0 uses a 16-bit length and ID followed by a 32-bit group ID.
        self.assertEqual(frame[:12], bytes.fromhex("534d4100 0004 02a0 00000001"))
        self.assertEqual(struct.unpack_from('>H', frame, 16)[0], 0x6069)
        self.assertEqual(struct.unpack_from('>H', frame, 12)[0], len(frame)-16-4)
        self.assertEqual(struct.unpack_from('>I', frame, 20)[0], 900000001)
        self.assertEqual(frame[28:32], b'\x01\x01\x04\x00')
        self.assertEqual(struct.unpack_from('>I', frame, 32)[0], 12000)
        self.assertEqual(struct.unpack_from('>Q', frame, 40)[0], round(12.345*3600000))
        self.assertEqual(struct.unpack_from('>I', frame, 52)[0], 0)
        self.assertEqual(frame[-4:], b'\0\0\0\0')
        self.assertEqual(len(frame), 72)

    def test_export(self):
        frame = bridge.build_frame(900000001, 270, -3210.2, 1.0, 2.0, 200)
        self.assertEqual(struct.unpack_from('>I', frame, 32)[0], 0)
        self.assertEqual(struct.unpack_from('>I', frame, 52)[0], 32102)

    def test_reject_negative_energy(self):
        with self.assertRaises(ValueError):
            bridge.build_frame(900000001, 270, 1.0, -1.0, 0.0, 1)

    def test_modbus_decode(self):
        regs = [0] * 55
        regs[0], regs[1] = 203, 105
        regs[18] = 0xFFF0
        regs[22] = 2
        regs[38], regs[39] = 0, 3000
        regs[46], regs[47] = 0, 8000
        regs[54] = 0
        self.assertEqual(bridge.decode_meter_registers(regs), (-1600, 8.0, 3.0))
        regs[0] = 101
        with self.assertRaises(ValueError):
            bridge.decode_meter_registers(regs)

    def test_scale_factor(self):
        regs = [0] * 55
        regs[0], regs[1] = 203, 105
        regs[18] = 105
        regs[22] = 0xFFFE
        regs[38], regs[39] = 0, 200
        regs[46], regs[47] = 0, 1000
        regs[54] = 1
        power, imp, exp = bridge.decode_meter_registers(regs)
        self.assertAlmostEqual(power, 1.05)
        self.assertAlmostEqual(imp, 10.0)
        self.assertAlmostEqual(exp, 2.0)

    def test_sunspec_invalid_value(self):
        regs = [0] * 55
        regs[0], regs[1] = 203, 105
        regs[18] = 0x8000
        with self.assertRaises(ValueError):
            bridge.decode_meter_registers(regs)
        regs[18] = 5
        regs[46], regs[47] = 65535, 65535
        with self.assertRaises(ValueError):
            bridge.decode_meter_registers(regs)

    def test_modbus_tcp_read_holding_registers_mock_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        errors = []
        def serve():
            try:
                with server:
                    conn, _ = server.accept()
                    with conn:
                        req = bridge._exact(conn, 12)
                        tx, proto, n, unit, fc, start, count = struct.unpack('>HHHBBHH', req)
                        assert (proto, n, unit, fc, start, count) == (0, 6, 1, 3, 100, 3)
                        pdu = bytes([3, 6]) + struct.pack('>HHH', 12, 34, 56)
                        res = struct.pack('>HHHB', tx, 0, 1 + len(pdu), unit) + pdu
                        conn.sendall(res[:4])
                        conn.sendall(res[4:])
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            result = bridge.read_holding_registers('127.0.0.1', port, 1, 100, 3)
            self.assertEqual(result, [12, 34, 56])
        finally:
            thread.join(timeout=3)
        self.assertEqual(errors, [])

    def test_swap_counters(self):
        opts = dict(modbus_host="x", modbus_port=502, modbus_unit_id=1, meter_model_base=40188,
                    power_sign="import_positive", swap_counters=True, max_abs_power_w=30000)
        regs = [0] * 55
        regs[0], regs[1] = 203, 105
        regs[38], regs[39], regs[46], regs[47] = 0, 2000, 0, 5000
        with patch.object(bridge, "read_holding_registers", return_value=regs):
            _, imp, exp = bridge.fetch_meter(opts)
            self.assertEqual((imp, exp), (2, 5))

    def test_sign_flip(self):
        opts = dict(modbus_host='x', modbus_port=502, modbus_unit_id=1,
                    meter_model_base=40188, power_sign='export_positive',
                    max_abs_power_w=30000)
        regs = [0] * 55
        regs[0], regs[1] = 203, 105
        regs[18], regs[22] = 1200, 0
        with patch.object(bridge, 'read_holding_registers', return_value=regs):
            self.assertEqual(bridge.fetch_meter(opts)[0], -1200)


if __name__ == '__main__':
    unittest.main()
