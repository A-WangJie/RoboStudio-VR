from _support import node_binary, prepare_artifacts
"""Production UI in Google Chrome; fake diagnostics never open a CAN socket."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import time
from threading import Thread
import unittest

from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.s1_can import parse_state
from backend.simulation import Simulation
from server import Handler

ROOT=Path(__file__).resolve().parents[1]
prepare_artifacts(ROOT)


class Fixture(HardwareDiagnostics):
    def __init__(self,lock):
        self.mode='normal';self.count=0
        super().__init__(self.inventory,self.probe_fixture,lock)

    def inventory(self):
        return [dict(device=f'can{i}',up=self.mode!='down',busState='ERROR-ACTIVE',bitrate=1000000,
            rxPackets=7,txPackets=7,rxErrors=0,txErrors=0) for i in range(2 if self.mode=='dual' else 1)]

    def probe_fixture(self,device,end,timeout):
        nodes=list(range(1,8 if end=='gripper' else 7))
        return dict(requiredNodes=nodes,respondingNodes=nodes,missingNodes=[],sentNodes=nodes,elapsedMs=600)

    def detect(self,value):
        self.count+=1
        if self.mode=='failure':raise OSError('测试检测超时，请重新检测')
        result=super().detect(value)
        if self.mode=='stale':result['checkedAtMs']=int(time.time()*1000)-20000
        return result


class MotorFixture:
    def __init__(self,fixture):
        self.fixture=fixture;self.code=0;self.commands=[];self.reads=0
    def close(self):pass
    def read(self,nodes,timeout):
        self.reads+=1
        code=8 if self.fixture.mode=='motor-fault' else self.code
        return [parse_state(struct.pack('=IB3x8s',0x10+n,8,bytes([(code<<4)|n,0x80,0,0x80,7,0xff,25,26])))
            for n in nodes if self.fixture.mode!='motor-partial' or n!=7]
    def command(self,nodes,action):
        self.commands.append((nodes,action))
        if self.fixture.mode!='motor-refuse':self.code=1 if action=='enable' else 0
        return nodes,None


class FixtureOperations(HardwareOperations):
    def operate(self,action,value):
        result=super().operate(action,value)
        if self.diagnostics.mode=='motor-stale':result['sampledAtMs']-=20000
        return result


class HardwareHandler(Handler):
    def log_message(self,*_):pass

    def do_GET(self):
        if self.path.startswith('/hardware-fixture'):
            mode=self.path.partition('?')[2]
            if mode:self.server.hardware_diagnostics.mode=mode
            self.json_response(200,dict(count=self.server.hardware_diagnostics.count,
                motorCommands=len(self.server.motor_fixture.commands),reads=self.server.motor_fixture.reads));return
        if self.path.split('?')[0]=='/':
            data=(ROOT/'app/index.html').read_text().replace('</body>','<script type="module" src="/hardware-test.js"></script></body>').encode()
        elif self.path=='/hardware-test.js':data=(ROOT/'tests/browser-hardware.js').read_bytes()
        else:return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)


class HardwareChromeTests(unittest.TestCase):
    def test_diagnostics_and_configuration(self):
        chrome=shutil.which('google-chrome')
        if not chrome:self.skipTest('Google Chrome unavailable')
        with tempfile.TemporaryDirectory(prefix='hardware-chrome-') as temp:
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(HardwareHandler,directory=str(ROOT/'app')))
            server.hardware_diagnostics=Fixture(Path(temp)/'detect.lock')
            server.motor_fixture=MotorFixture(server.hardware_diagnostics)
            server.hardware_operations=FixtureOperations(server.hardware_diagnostics,lambda device:server.motor_fixture,Path(temp)/'audit.jsonl')
            server.simulation=Simulation(start_worker=False)
            Thread(target=server.serve_forever,daemon=True).start()
            try:
                result=subprocess.run([node_binary(),
                    str(ROOT/'tests/chrome-driver.cjs'),chrome,temp,f'http://127.0.0.1:{server.server_port}/',
                    str(ROOT/'artifacts/screenshots/hardware-configuration.png'),str(ROOT/'artifacts/reports/hardware-browser-checks.json')],
                    capture_output=True,text=True,timeout=55)
                self.assertEqual(result.returncode,0,result.stderr[-5000:])
                report=json.loads((ROOT/'artifacts/reports/hardware-browser-checks.json').read_text())
                self.assertTrue(report['ok'],report)
                print(json.dumps(report,ensure_ascii=False))
            finally:
                server.shutdown();server.server_close();server.simulation.close()


if __name__=='__main__':unittest.main()
