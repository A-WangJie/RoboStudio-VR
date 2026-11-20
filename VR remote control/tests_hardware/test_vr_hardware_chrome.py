"""Production RS pages and VR routing in Chrome; all motors/input are in memory."""
from copy import deepcopy
from functools import partial
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'VR remote control'));sys.path.insert(0,str(ROOT/'tests'))
from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.hardware_motion import HardwareMotion
from backend.simulation import Simulation
from hardware_control import VRHardwareControl
from server import Handler
from test_hardware_mouse import MotionTransport
from test_vr_hardware import packet
from bridge.simulation_link import SimulationLink


class VRHandler(Handler):
    def log_message(self,*args):pass

    def do_GET(self):
        if self.path=='/':
            data=(ROOT/'app/index.html').read_text().replace('</body>','<script type="module" src="/vr-hardware-test.js"></script></body>').encode()
        elif self.path=='/vr-hardware-test.js':data=Path(__file__).with_name('browser-vr-hardware.js').read_bytes()
        elif self.path=='/vr-fixture':
            m=self.server.hardware_motion;v=self.server.vr_hardware;t=self.server.motor_fixture
            self.json_response(200,dict(writes=t.writes,enabled=t.enabled,q=t.q,state=v.state()));return
        elif self.path=='/api/vr-bridge/state':
            s=self.server.telemetry();s.update(count=10,simulation=dict(vrMode=False,enabled=False),connection=dict(mode='usb'))
            self.json_response(200,s);return
        else:return super().do_GET()
        self.send_response(200);self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def do_POST(self):
        if self.path=='/vr-fixture':
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            for key,item in value.get('right',{}).items():self.server.packet['right'][key]=item
            if value.get('resetFixturePose'):
                self.server.motor_fixture.q[:6]=self.server.simulation.spec['vrGrabRadians']
            if 'uiInteracting' in value:self.server.packet['uiInteracting']=value['uiInteracting']
            if 'delayStart' in value:self.server.delay_start=value['delayStart']
            if 'shortcut' in value:
                action=value['shortcut']
                result=self.server.link.enable() if action=='A' else self.server.link.mode_command('reset')
                self.json_response(200,result);return
            self.json_response(200,dict(ok=True));return
        return super().do_POST()

    def vr_hardware(self):
        vr=super().vr_hardware()
        if self.path=='/api/hardware/vr/start' and getattr(self.server,'delay_start',False):time.sleep(.5)
        return vr


class VRHardwareChromeTests(unittest.TestCase):
    def test_vr_takeover_routing_recovery_and_pending_navigation(self):
        chrome=shutil.which('google-chrome')
        if not chrome:self.skipTest('Google Chrome not installed')
        with tempfile.TemporaryDirectory(prefix='vr-hardware-chrome-') as directory:
            config=dict(layout='single',timeoutMs=500,arms=[dict(id=c,device=f'can{i}',bitrate=1000000,endEffector='gripper') for i,c in enumerate('AB')])
            configfile=Path(directory)/'arms.json';configfile.write_text(json.dumps(dict(connection=dict(layout='single',timeoutMs=500),arms=config['arms'])))
            sim=Simulation(start_worker=False);motor=MotionTransport('can0');motor.q[:6]=sim.spec['vrGrabRadians']
            diagnostics=HardwareDiagnostics(lambda:[dict(device='can0',up=True,bitrate=1000000,busState='ERROR-ACTIVE')],lock_path=Path(directory)/'lock')
            operations=HardwareOperations(diagnostics,lambda _:motor,Path(directory)/'audit.jsonl')
            motion=HardwareMotion(operations,sim,configfile)
            http=ThreadingHTTPServer(('127.0.0.1',0),partial(VRHandler,directory=str(ROOT/'app')))
            http.simulation=sim;http.hardware_motion=motion;http.motor_fixture=motor;http.hardware_operations=operations;http.hardware_diagnostics=diagnostics
            http.packet=packet()
            def telemetry():
                p=deepcopy(http.packet);p['seq']=int(time.monotonic()*1000);p['timeMs']=time.monotonic()*1000
                return dict(status='live',packet=p,ageMs=0,error='',network=dict(extraDelayMs=0))
            http.telemetry=telemetry;vr=VRHardwareControl(motion,telemetry);http.vr_hardware=vr
            def request(path,body=None):
                if path.endswith('/state'):return vr.state()
                if path.endswith('/command'):return vr.command(body['action'])
                raise AssertionError('Hardware shortcut reached simulation')
            http.link=SimulationLink(None,request)
            Thread(target=http.serve_forever,daemon=True).start()
            try:
                report=ROOT/'VR remote control/artifacts/reports/vr-hardware-checks.json'
                report.parent.mkdir(parents=True,exist_ok=True)
                screenshot=ROOT/'VR remote control/artifacts/screenshots/vr-hardware-control.png'
                screenshot.parent.mkdir(parents=True,exist_ok=True)
                process=subprocess.run([os.environ.get('NODE_BINARY') or shutil.which('node') or str(Path.home()/'.local/opt/chatgpt/resources/cua_node/bin/node'),str(ROOT/'tests/chrome-driver.cjs'),chrome,directory,
                    f'http://127.0.0.1:{http.server_port}/',str(screenshot),str(report)],capture_output=True,text=True,timeout=55)
                self.assertEqual(process.returncode,0,process.stderr[-4000:])
                checks=json.loads(report.read_text());self.assertTrue(checks['ok'],checks)
                print(json.dumps(checks,ensure_ascii=False))
            finally:
                vr.stop();motion.stop(hold=False);sim.close();http.shutdown();http.server_close()


if __name__=='__main__':unittest.main()
