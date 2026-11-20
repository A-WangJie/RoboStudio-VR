"""Lifecycle checks without interrupting the user's active bridge or Quest."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VR_ROOT))
from bridge_service import BridgeService

spec = importlib.util.spec_from_file_location('workbench_server', VR_ROOT.parent / 'server.py')
workbench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workbench)


class BridgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.service = BridgeService(self.root, f'http://127.0.0.1:{self.port}/api/state', timeout=3)
        (self.root / 'stub.py').write_text('''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, time
from pathlib import Path
with Path('starts').open('a') as f: f.write('start\\n')
time.sleep(.3)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({'status':'waiting','connection':{},'simulation':{}}).encode())
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
'''.replace('PORT', str(self.port)))
        (self.root / 'start-bridge.sh').write_text(f'exec "{sys.executable}" stub.py\n')

    def tearDown(self):
        if self.service.process is not None:
            self.service.process.terminate()
            self.service.process.wait(timeout=3)
        self.temp.cleanup()

    def test_start_concurrent_and_reuse_from_another_workbench(self):
        other = BridgeService(self.root, self.service.state_url, timeout=3)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda service: service.setup(), [self.service, other]))
        # Whichever workbench won owns the child for cleanup.
        self.service.process = self.service.process or other.process
        self.assertTrue(all(result['running'] for result in results))
        self.assertIn('已在运行', self.service.setup()['message'])
        self.assertEqual((self.root / 'starts').read_text().splitlines(), ['start'])

    def test_failed_start_reports_log(self):
        (self.root / 'start-bridge.sh').write_text('exit 7\n')
        with self.assertRaisesRegex(RuntimeError, '启动失败.*bridge-runtime.log'):
            self.service.setup()

    def test_timeout_retries_pending_process_without_duplicate(self):
        self.service.timeout = .05
        with self.assertRaisesRegex(RuntimeError, '尚未就绪'):
            self.service.setup()
        self.service.timeout = 3
        self.assertTrue(self.service.setup()['running'])
        self.assertEqual((self.root / 'starts').read_text().splitlines(), ['start'])

    def test_local_endpoint_and_origin(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), workbench.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        address = f'http://127.0.0.1:{http.server_port}'
        try:
            with patch.object(workbench, 'bridge_service', self.service):
                for origin in (None, 'https://example.com'):
                    req = Request(address + '/api/vr-bridge/setup', data=b'{}',
                                  headers={'Origin': origin} if origin else {})
                    with self.assertRaises(HTTPError) as error:
                        urlopen(req)
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
                self.assertIsNone(self.service.process)
                req = Request(address + '/api/vr-bridge/setup', data=b'{}',
                              headers={'Origin': address, 'Content-Type': 'application/json'})
                with urlopen(req) as response:
                    self.assertTrue(json.load(response)['running'])
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
