from _support import node_binary, prepare_artifacts
"""Mouse-to-hardware UI in Google Chrome, using an entirely fake CAN device."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread
import unittest

from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.hardware_motion import HardwareMotion
from backend.simulation import Simulation
from server import Handler
from test_hardware_mouse import MotionTransport

ROOT=Path(__file__).resolve().parents[1]
prepare_artifacts(ROOT)


class MouseHandler(Handler):
    def log_message(self,*args):pass
    def do_POST(self):
        if self.path=='/mouse-fixture/loss':
            self.server.motor_fixture.missing=True
            self.json_response(200,dict(ok=True));return
        return super().do_POST()
    def do_GET(self):
        if self.path=='/':
            data=(ROOT/'app/index.html').read_text().replace('</body>','<script type="module" src="/real-mouse-test.js"></script></body>').encode()
        elif self.path=='/real-mouse-test.js':data=(ROOT/'tests/browser-hardware-mouse.js').read_bytes()
        elif self.path=='/mouse-fixture':
            t=self.server.motor_fixture
            motion=self.server.hardware_motion
            self.json_response(200,dict(writes=t.writes,enabled=t.enabled,q=t.q,closed=t.closed,
                target=motion.target.tolist() if motion.active else None));return
        else:return super().do_GET()
        self.send_response(200);self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


class HardwareMouseChromeTests(unittest.TestCase):
    def test_mouse_hardware_takeover_and_stops(self):
        chrome=shutil.which('google-chrome')
        if not chrome:self.skipTest('Google Chrome not installed')
        with tempfile.TemporaryDirectory(prefix='hardware-mouse-chrome-') as directory:
            config=dict(layout='single',timeoutMs=500,arms=[dict(id=c,device=f'can{i}',bitrate=1000000,endEffector='gripper') for i,c in enumerate('AB')])
            configfile=Path(directory)/'arms.json'
            configfile.write_text(json.dumps(dict(connection=dict(layout='single',timeoutMs=500),arms=config['arms'])))
            simulation=Simulation(start_worker=False)
            motor=MotionTransport('can0')
            diagnostics=HardwareDiagnostics(lambda:[dict(device='can0',up=True,bitrate=1000000,busState='ERROR-ACTIVE')],lock_path=Path(directory)/'lock')
            operations=HardwareOperations(diagnostics,lambda device:motor,Path(directory)/'audit.jsonl')
            motion=HardwareMotion(operations,simulation,configfile)
            http=ThreadingHTTPServer(('127.0.0.1',0),partial(MouseHandler,directory=str(ROOT/'app')))
            http.simulation=simulation;http.hardware_motion=motion;http.hardware_operations=operations;http.hardware_diagnostics=diagnostics;http.motor_fixture=motor
            Thread(target=http.serve_forever,daemon=True).start()
            try:
                report=ROOT/'artifacts/reports/hardware-mouse-checks.json'
                result=subprocess.run([node_binary(),str(ROOT/'tests/chrome-driver.cjs'),chrome,directory,
                    f'http://127.0.0.1:{http.server_port}/',str(ROOT/'artifacts/screenshots/hardware-mouse-control.png'),str(report)],capture_output=True,text=True,timeout=55)
                self.assertEqual(result.returncode,0,result.stderr[-4000:])
                checks=json.loads(report.read_text());self.assertTrue(checks['ok'],checks)
                print(json.dumps(checks,ensure_ascii=False))
            finally:motion.stop(hold=False);simulation.close();http.shutdown();http.server_close()


if __name__=='__main__':unittest.main()
