from _support import node_binary, prepare_artifacts
"""Chrome end-to-end tests using real MuJoCo and production UI code."""
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
from threading import Thread
import unittest

from backend.simulation import Simulation
from server import Handler

ROOT = Path(__file__).resolve().parents[1]
prepare_artifacts(ROOT)


class BrowserHandler(Handler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path == '/test-step':
            self.server.simulation.step(250)
            self.json_response(200, {'ok': True})
            return
        super().do_POST()

    def do_GET(self):
        if self.path.split('?')[0] == '/':
            data = (ROOT / 'app/index.html').read_text().replace('</body>', '<script type="module" src="/test-driver.js"></script></body>').encode()
        elif self.path == '/test-driver.js':
            data = (ROOT / 'tests/browser-teleop.js').read_bytes()
        else:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TeleopChromeTests(unittest.TestCase):
    def test_browser_control_chain(self):
        self.run_browser()

    def test_backend_disconnect(self):
        self.run_browser(disconnect=True)

    def run_browser(self, disconnect=False):
        chrome = shutil.which('google-chrome')
        if not chrome:
            self.skipTest('Google Chrome is required')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(BrowserHandler, directory=str(ROOT/'app')))
        server.simulation = Simulation(start_worker=False)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(prefix='s1-teleop-chrome-') as profile:
                node = node_binary()
                report = 'teleop-disconnect-checks.json' if disconnect else 'teleop-browser-checks.json'
                report_path = ROOT/'artifacts/reports'/report
                command = [node, str(ROOT/'tests/chrome-driver.cjs'), chrome, profile,
                    f'http://127.0.0.1:{server.server_port}/' + ('?disconnect=1' if disconnect else ''),
                    '-' if disconnect else str(ROOT/'artifacts/screenshots/teleop-stage2.png'), str(report_path)]
                process = subprocess.run(command, text=True, capture_output=True, timeout=50)
                self.assertEqual(process.returncode, 0, process.stderr[-6000:])
                result = json.loads(report_path.read_text())
                self.assertTrue(result['ok'], result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            server.simulation.close()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
