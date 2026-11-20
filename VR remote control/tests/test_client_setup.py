import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from client_setup import ClientSetup
from connection import Connection
from wear_mode import WearMode


class ClientSetupTests(unittest.TestCase):
    def setUp(self):
        device=patch.dict("os.environ", {"QUEST_SERIAL":"test-quest"})
        device.start();self.addCleanup(device.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.connection = Connection(self.root / 'connection.json')
        self.connection.snapshot = lambda: {'addresses': ['192.168.2.67', '198.18.0.1']}
        self.calls = []
        self.payloads = []
        self.fail_usb = False
        self.fail_wireless = False
        self.delayed_listener = False
        self.wear = WearMode(Mock(), self.run_adb, mode=lambda: self.connection.mode,
                             config=self.root / 'wireless-adb.json')
        self.wear.wireless = '172.20.10.3:5555'
        self.simulation = Mock()
        self.recorder = Mock()
        self.disconnect = Mock()
        self.setup = ClientSetup(self.connection, self.wear, self.simulation, self.recorder, self.disconnect)

    def run_adb(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.fail_usb and cmd[-1] == 'get-state' and ':' not in cmd[2]:
            return SimpleNamespace(returncode=1, stdout='', stderr='unauthorized')
        if cmd[1] == 'connect':
            if self.fail_wireless or self.delayed_listener:
                self.delayed_listener = False
                return SimpleNamespace(returncode=1, stdout='', stderr='failed to connect')
        if 'push' in cmd:
            self.payloads.append(json.loads(Path(cmd[-2]).read_text()))
        if cmd[-1] == 'get-state': output = 'device'
        elif cmd[-1] == 'wlan0': output = '15: wlan0 inet 192.168.2.134/24 brd 192.168.2.255 scope global wlan0'
        else: output = 'ok'
        return SimpleNamespace(returncode=0, stdout=output, stderr='')

    def test_wifi_sets_selected_mode_and_refreshes_wireless_address(self):
        result = self.setup.configure({'mode': 'wifi', 'host': '192.168.2.67'})
        self.assertTrue(result['synced'] and result['wirelessReady'])
        self.assertEqual(self.payloads, [dict(mode='wifi', host='192.168.2.67', port='8766', code=self.connection.token)])
        self.assertEqual(self.connection.mode, 'wifi')
        self.disconnect.assert_called_once()
        self.assertEqual(self.wear.snapshot()['wirelessEndpoint'], '192.168.2.134:5555')
        self.assertEqual(json.loads((self.root / 'wireless-adb.json').read_text()), dict(host='192.168.2.134', port=5555))
        self.assertTrue(any(c[-3:] == ['shell', 'getprop', 'ro.product.model'] for c in self.calls))
        self.assertFalse(any('broadcast' in c for c in self.calls))
        self.assertFalse(any('reverse' in c for c in self.calls))
        self.simulation.disable.assert_called_once()
        self.recorder.stop.assert_called_once()

    def test_usb_does_not_require_wifi_or_configure_wireless(self):
        result = self.setup.configure({'mode': 'usb'})
        self.assertTrue(result['synced'])
        self.assertTrue(any('reverse' in c for c in self.calls))
        self.assertFalse(any('wlan0' in c or 'tcpip' in c for c in self.calls))
        self.disconnect.assert_not_called()

    def test_missing_usb_does_not_change_active_connection(self):
        self.fail_usb = True
        with self.assertRaisesRegex(ValueError, 'USB.*允许调试'):
            self.setup.configure({'mode': 'wifi', 'host': '192.168.2.67'})
        self.assertEqual(self.connection.mode, 'usb')
        self.simulation.disable.assert_not_called()
        self.assertEqual(self.payloads, [])

    def test_wrong_network_does_not_push_or_switch_mode(self):
        with self.assertRaisesRegex(ValueError, '同一网段'):
            self.setup.configure({'mode': 'wifi', 'host': '198.18.0.1'})
        self.assertEqual(self.connection.mode, 'usb')
        self.assertEqual(self.payloads, [])

    def test_partial_failure_is_explicit_and_retry_succeeds(self):
        self.fail_wireless = True
        with patch('wear_mode.time.sleep'):
            result = self.setup.configure({'mode': 'wifi', 'host': '192.168.2.67'})
        self.assertTrue(result['synced'])
        self.assertFalse(result['wirelessReady'])
        self.assertIn('但自由摘戴无线调试未配置成功', result['message'])
        self.fail_wireless = False
        self.assertTrue(self.setup.configure({'mode': 'wifi', 'host': '192.168.2.67'})['wirelessReady'])

    def test_tcpip_listener_startup_is_retried(self):
        self.delayed_listener = True
        with patch('wear_mode.time.sleep'):
            result = self.setup.configure({'mode': 'wifi', 'host': '192.168.2.67'})
        self.assertTrue(result['wirelessReady'])
        self.assertEqual(len([c for c in self.calls if c[1] == 'connect']), 2)

    def test_duplicate_request_is_rejected(self):
        with self.setup.lock:
            with self.assertRaisesRegex(ValueError, '正在配置'):
                self.setup.configure({'mode': 'usb'})
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
