"""No real CAN: verify ownership and absence of initialization motor writes."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from S1_SDK import safe_can
from S1_SDK.device_session import DeviceSession
from S1_SDK.native_session import OwnedNativeArm

class SharedSDKTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'locks'
    def session(self, device):return DeviceSession(device,self.directory)
    def test_rs_uses_exact_sdk_implementation(self):
        import backend.s1_can as rs
        from backend.hardware import probe_can
        self.assertIs(rs,safe_can);self.assertIs(probe_can,safe_can.probe_can)
    def test_device_ownership_across_processes(self):
        with self.session('can0'):
            code="from S1_SDK.device_session import DeviceSession; DeviceSession('can0', %r).acquire()" % str(self.directory)
            p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0);self.assertIn('已被终端或 RS 占用',p.stderr)
            with self.session('can1'):pass
        with self.session('can0'):pass
    def test_busy_sdk_native_constructor_is_never_called(self):
        with self.session('can0'),patch('S1_SDK.native_session.DeviceSession',side_effect=self.session):
            factory=Mock()
            with self.assertRaisesRegex(RuntimeError,'占用'):OwnedNativeArm(factory,'can0',0,0)
            factory.assert_not_called()
    def test_failed_native_construction_releases_ownership(self):
        with patch('S1_SDK.native_session.DeviceSession',side_effect=self.session):
            with self.assertRaisesRegex(RuntimeError,'failed'):
                OwnedNativeArm(Mock(side_effect=RuntimeError('failed')),'can0',0,0)
        with self.session('can0'):pass
    def test_native_close_disables_once_then_releases(self):
        native=Mock()
        with patch('S1_SDK.native_session.DeviceSession',side_effect=self.session):
            arm=OwnedNativeArm(Mock(return_value=native),'can0',0,0)
        arm.close();arm.close();native.disable.assert_called_once()
        with self.session('can0'):pass
    def test_open_and_close_send_no_commands(self):
        sock=Mock()
        with patch('S1_SDK.safe_can.DeviceSession',side_effect=self.session),patch('S1_SDK.safe_can.socket.socket',return_value=sock):
            t=safe_can.S1Can('can0');t.close()
        sock.send.assert_not_called();sock.close.assert_called_once()
        with self.session('can0'):pass
    def test_socket_failure_releases_ownership(self):
        with patch('S1_SDK.safe_can.DeviceSession',side_effect=self.session),patch('S1_SDK.safe_can.socket.socket',side_effect=OSError('bind')):
            with self.assertRaises(OSError):safe_can.S1Can('can0')
        with self.session('can0'):pass
    def test_safe_enable_rejects_missing_or_faulty_feedback(self):
        for samples in [[],[dict(node=n,fault=n==3,positionValid=True,enabled=False) for n in range(1,8)]]:
            transport=Mock();transport.read.return_value=samples
            with patch('S1_SDK.safe_can.S1Can',return_value=transport):
                with self.assertRaises(RuntimeError):safe_can.set_motor_state('can0','gripper','enable')
            transport.command.assert_not_called();transport.close.assert_called_once()
    def test_joint_and_teaching_end_nodes(self):
        self.assertEqual(safe_can.required_nodes('teach'),[1,2,3,4,5,6,8])
        self.assertEqual(safe_can.required_nodes('gripper'),list(range(1,8)))
    @unittest.skipUnless(os.environ.get("DK_TEST_LOCAL_TERMINAL_PATCHES") == "1", "Optional local terminal-script patches are not distributed with DK")
    def test_follower_init_failure_never_enables_leader(self):
        import S1_SDK
        root=Path(S1_SDK.__file__).parents[2];examples=root/'examples/python'
        with patch.object(sys,'path',[str(examples),*sys.path]):
            module=runpy.run_path(str(examples/'teleop_demo.py'))
        master=Mock();fake_args=types.SimpleNamespace(master_dev='can0',slaver_dev='can1',arm_version='V1')
        module['main'].__globals__.update(create_parser=Mock(return_value=Mock(parse_args=Mock(return_value=fake_args))),
            validate_device=Mock(),arm_options=lambda *a,**kw:{'dev':kw['dev']},
            S1_arm=Mock(side_effect=[master,RuntimeError('slave failed')]))
        with self.assertRaisesRegex(RuntimeError,'slave failed'),contextlib.redirect_stdout(io.StringIO()):module['main']()
        master.enable.assert_not_called();master.close.assert_called_once()
    @unittest.skipUnless(os.environ.get("DK_TEST_LOCAL_TERMINAL_PATCHES") == "1", "Optional local terminal-script patches are not distributed with DK")
    def test_terminal_enable_calls_safe_sdk_not_native_constructor(self):
        import S1_SDK
        examples=Path(S1_SDK.__file__).parents[2]/'examples/python'
        with patch.object(sys,'path',[str(examples),*sys.path]):module=runpy.run_path(str(examples/'enable.py'))
        args=types.SimpleNamespace(arm_version='V1',dev='can0',end='gripper')
        native=Mock();module['main'].__globals__.update(create_parser=Mock(return_value=Mock(parse_args=Mock(return_value=args))),S1_arm=native)
        with patch('common.validate_device'),patch('S1_SDK.safe_can.set_motor_state',return_value={'verified':True}) as operation,contextlib.redirect_stdout(io.StringIO()):module['main']()
        operation.assert_called_once_with('can0','gripper','enable');native.assert_not_called()

if __name__=='__main__':unittest.main()
