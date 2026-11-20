import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from recording import Recorder
from teaching_capture import TeachingCapture, validate_options, validate_sample


class TeachingTests(unittest.TestCase):
    def test_validation(self):
        for config in ({}, {'devices':['can0','can0']}, {'devices':['../x']}, {'devices':['can0'],'rateHz':True}):
            with self.assertRaises(ValueError): validate_options(config)
        with self.assertRaises(ValueError):
            validate_sample({'source':'teaching-sdk','arms':[{'device':'can0','jointsRad':[float('nan')]*6}]},['can0'])

    def test_sdk_recording_and_disconnect(self):
        code="""import json,sys,time
config=json.loads(sys.argv[1])
for seq in range(8):
 print('ROBODATA_SAMPLE '+json.dumps(dict(source='teaching-sdk',seq=seq,arms=[dict(device=d,jointsRad=[.1,.2,.3,.4,.5,.6]) for d in config['devices']])),flush=True)
 time.sleep(.05)
"""
        with tempfile.TemporaryDirectory() as directory:
            recorder=Recorder(directory)
            capture=TeachingCapture(recorder,[sys.executable,'-u','-c',code])
            try:
                capture.start('实物测试',{'devices':['can0','can1']})
                self.assertEqual(recorder.snapshot()['source'],'teaching-sdk')
                capture.thread.join(3)
                self.assertFalse(capture.thread.is_alive())
                rows=[json.loads(line) for line in Path(recorder.snapshot()['file']).read_text().splitlines()]
                self.assertFalse(rows[0]['metadata']['simulationOnly'])
                self.assertTrue(rows[0]['metadata']['readOnly'])
                self.assertEqual(rows[-1]['reason'],'sdk_disconnected')
                self.assertGreater(rows[-1]['frames'],1)
                self.assertEqual(len(rows[1]['input']['arms']),2)
                self.assertIsNone(rows[1]['simulation'])
                capture.start('再次采集',{'devices':['can0']})
                self.assertTrue(recorder.snapshot()['active'])
                self.assertGreaterEqual(recorder.snapshot()['frames'],1)
            finally: capture.stop()

    def test_failure_creates_no_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder=Recorder(directory)
            capture=TeachingCapture(recorder,[sys.executable,'-u','-c',"print('ROBODATA_ERROR 未连接实体设备',flush=True)"])
            with self.assertRaisesRegex(ValueError,'未连接实体设备'):
                capture.start('x',{'devices':['can0']})
            self.assertFalse(recorder.snapshot()['active'])
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_vr_disconnect_does_not_stop_teaching(self):
        import server
        with tempfile.TemporaryDirectory() as directory:
            old=server.recorder
            try:
                server.recorder=Recorder(directory)
                server.recorder.start('x',{'source':'teaching-sdk'})
                server.stop_vr_recording('producer_disconnected')
                self.assertTrue(server.recorder.snapshot()['active'])
            finally:
                server.recorder.stop();server.recorder=old

    def test_readonly_guard_blocks_native_transport_write(self):
        # Verify in a child: cannot alter this test process's syscall policy.
        code="""import os,errno
from readonly_guard import install
r,w=os.pipe()
install()
try: os.write(w,b'control')
except OSError as e: assert e.errno==errno.EPERM
else: raise AssertionError('write unexpectedly permitted')
print('guard-ok')
"""
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'bridge'))
        result=subprocess.run([sys.executable,'-c',code],env=env,text=True,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('guard-ok',result.stdout)

    def test_real_worker_missing_interface(self):
        worker=Path(__file__).resolve().parents[1]/'bridge/teaching_reader.py'
        # Missing-interface handling must not depend on a workstation SDK install.
        with tempfile.TemporaryDirectory() as sdk:
            (Path(sdk)/'src/S1_SDK/hardware').mkdir(parents=True)
            result=subprocess.run([sys.executable,str(worker),json.dumps({'devices':['rd_missing0']})],env=dict(os.environ,ROBODATA_S1_SDK=sdk),capture_output=True,text=True,timeout=5)
        self.assertIn('ROBODATA_ERROR 未找到 CAN 接口',result.stdout)
        self.assertNotIn('ROBODATA_SAMPLE ',result.stdout)
