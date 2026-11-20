import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from wear_mode import WearMode

class WearTests(unittest.TestCase):
    def setUp(self):
        device=patch.dict("os.environ", {"QUEST_SERIAL":"test-quest"})
        device.start();self.addCleanup(device.stop)

    def test_toggle_and_default_restore(self):
        calls=[];stops=[]
        def run(cmd,**kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0,stdout='device' if cmd[-1]=='get-state' else 'Broadcast completed: result=0',stderr='')
        mode=WearMode(stops.append,run)
        mode.restore();self.assertFalse(mode.snapshot()['enabled'])
        mode.set(True);self.assertTrue(mode.snapshot()['enabled'])
        mode.set(False);self.assertFalse(mode.snapshot()['enabled'])
        self.assertEqual(len(stops),3)
        self.assertEqual(calls[-1][-1],'com.oculus.vrpowermanager.automation_disable')
        self.assertTrue(any('com.oculus.vrpowermanager.prox_close' in c for c in calls))
    def test_failure_not_reported_as_off(self):
        mode=WearMode(lambda _:None,lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr='unauthorized'))
        mode.restore();self.assertIsNone(mode.snapshot()['enabled'])
        self.assertFalse(mode.snapshot()['busy'])
        self.assertIn('unauthorized',mode.snapshot()['message'])
    def test_wireless_commands_use_network_target_without_reverse(self):
        calls=[]
        def run(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout='device' if cmd[-1]=='get-state' else 'ok', stderr='')
        mode=WearMode(lambda _:None,run,mode=lambda:'wifi')
        mode.configure_wireless({'host':'192.168.1.20','port':5555})
        mode.set(True);mode.set(False)
        self.assertTrue(mode.snapshot()['wirelessReady'])
        self.assertFalse(any('reverse' in c for c in calls))
        broadcasts=[c for c in calls if 'broadcast' in c]
        self.assertEqual(len(broadcasts),2)
        self.assertTrue(all(c[1:3]==['-s','192.168.1.20:5555'] for c in broadcasts))

    def test_wireless_failure_does_not_report_enabled(self):
        mode=WearMode(lambda _:None,mode=lambda:'wifi')
        with self.assertRaises(ValueError):mode.set(True)
        self.assertIsNone(mode.snapshot()['enabled'])
        self.assertFalse(mode.snapshot()['wirelessReady'])
        for host,port in [('127.0.0.1',5555),('192.168.1.2',0),('192.168.1.2;echo x',5555)]:
            with self.assertRaises(ValueError):mode.endpoint(host,port)

    def test_usb_auto_selection_ignores_old_wireless_address(self):
        calls=[]
        def run(cmd, **kw):
            calls.append(cmd)
            if cmd == ['adb', 'devices']:
                return SimpleNamespace(returncode=0, stdout='List of devices attached\nquest-usb\tdevice\n192.168.2.134:5555\toffline\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='device' if cmd[-1]=='get-state' else 'ok', stderr='')
        with patch.dict('os.environ', {'QUEST_SERIAL':''}):
            mode=WearMode(lambda _:None, run)
            mode.wireless='192.168.2.134:5555'
            mode.set(True);mode.set(False)
        broadcasts=[c for c in calls if 'broadcast' in c]
        self.assertEqual(len(broadcasts),2)
        self.assertTrue(all(c[1:3]==['-s','quest-usb'] for c in broadcasts))
        self.assertFalse(any('connect' in c for c in calls))

    def test_bool_required(self):
        mode=WearMode(lambda _:None)
        with self.assertRaises(ValueError):mode.set('false')

if __name__=='__main__':unittest.main()
