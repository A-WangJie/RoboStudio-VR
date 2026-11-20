from _support import node_binary, prepare_artifacts
"""Pointer, wheel and IK behavior in real Google Chrome with isolated MuJoCo."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread
import unittest

from backend.simulation import Simulation
from server import Handler

ROOT = Path(__file__).resolve().parents[1]
prepare_artifacts(ROOT)


class MouseHandler(Handler):
    def log_message(self, *_): pass

    def do_GET(self):
        if self.path == '/':
            data=(ROOT/'app/index.html').read_text().replace('</body>', '<script type="module" src="/mouse-test.js"></script></body>').encode()
        elif self.path == '/mouse-test.js': data=(ROOT/'tests/browser-mouse-follow.js').read_bytes()
        else: return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class MouseFollowChromeTests(unittest.TestCase):
    def test_mouse_follow_and_wheel(self):
        chrome=shutil.which('google-chrome')
        if not chrome: self.skipTest('Google Chrome unavailable')
        http=ThreadingHTTPServer(('127.0.0.1',0),partial(MouseHandler,directory=str(ROOT/'app')))
        http.simulation=Simulation(start_worker=False)
        http.simulation.command(dict(type='joints',joints=[0,1.05,1.55,.5,0,0],gripper=40))
        Thread(target=http.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(prefix='mouse-follow-chrome-') as profile:
                report=ROOT/'artifacts/reports/mouse-follow-checks.json'
                result=subprocess.run([node_binary(),
                    str(ROOT/'tests/chrome-driver.cjs'),chrome,profile,f'http://127.0.0.1:{http.server_port}/',
                    str(ROOT/'artifacts/screenshots/mouse-follow.png'),str(report)],capture_output=True,text=True,timeout=55)
                self.assertEqual(result.returncode,0,result.stderr[-4000:])
                data=json.loads(report.read_text())
                self.assertTrue(data['ok'],data)
                print(json.dumps(data,ensure_ascii=False))
        finally:
            http.simulation.close();http.shutdown();http.server_close()


if __name__ == '__main__': unittest.main()
