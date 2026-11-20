from _support import node_binary, prepare_artifacts
"""Shared configuration and honest offline teaching controls in real Chrome."""
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


class TeachingHandler(Handler):
    def log_message(self, *_): pass

    def do_GET(self):
        if self.path.split('?')[0] == '/':
            data = (ROOT / 'app/index.html').read_text().replace('</body>', '<script type="module" src="/teaching-test.js"></script></body>').encode()
        elif self.path == '/teaching-test.js':
            data = (ROOT / 'tests/browser-teaching.js').read_bytes()
        else:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TeachingChromeTests(unittest.TestCase):
    def test_shared_configuration_and_mapping_preview(self):
        chrome = shutil.which('google-chrome')
        if not chrome: self.skipTest('Google Chrome unavailable')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(TeachingHandler, directory=str(ROOT/'app')))
        server.simulation = Simulation(start_worker=False)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(prefix='teaching-chrome-') as profile:
                node = node_binary()
                report = ROOT / 'artifacts/reports/teaching-browser-checks.json'
                screenshot = ROOT / 'artifacts/screenshots/teaching-module.png'
                result = subprocess.run([node, str(ROOT/'tests/chrome-driver.cjs'), chrome,
                    profile, f'http://127.0.0.1:{server.server_port}/', str(screenshot), str(report)],
                    text=True, capture_output=True, timeout=55)
                self.assertEqual(result.returncode, 0, result.stderr[-5000:])
                data = json.loads(report.read_text())
                self.assertTrue(data['ok'], data)
                print(json.dumps(data, ensure_ascii=False))
        finally:
            server.simulation.close()
            server.shutdown()
            server.server_close()


if __name__ == '__main__': unittest.main()
