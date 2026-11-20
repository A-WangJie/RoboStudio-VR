from _support import node_binary, prepare_artifacts
"""Regression tests in real headless Google Chrome; fixtures never edit app files."""
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import shutil
import subprocess
import os
import signal
import tempfile
from threading import Thread
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
prepare_artifacts(ROOT)


class FixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        scenario = self.server.scenario
        if path in ('/vr-ui/panels.js', '/vr-ui/hardware.js', '/vr-ui/panels.css'):
            data = (ROOT/'VR remote control/ui'/path.rsplit('/',1)[1]).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript' if path.endswith('.js') else 'text/css')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data)
            return
        if (scenario == 'config404' and path.endswith('/model.json')) or (
                scenario == 'asset404' and path.endswith('/2_Link.STL')) or (
                scenario == 'module404' and path == '/js/errors.js'):
            self.send_error(404)
            return
        data = None
        if scenario == 'invalidJSON' and path.endswith('/model.json'):
            data = b'{invalid json'
        elif scenario == 'invalidSTL' and path.endswith('/2_Link.STL'):
            data = b'solid empty\nendsolid empty'
        elif scenario in ('fallback', 'rendererBug', 'frameBug') and path == '/js/renderer.js':
            data = (ROOT / 'app/js/renderer.js').read_text()
            injection = ('canvas.getContext = () => null;' if scenario in ('fallback', 'frameBug') else
                         'canvas.getContext = () => ({}); createWebGL = () => { throw new TypeError("injected renderer bug"); };')
            data = data.replace('  let context;', injection + '\n  let context;').encode()
        elif scenario == 'frameBug' and path == '/js/canvas-renderer.js':
            data = (ROOT / 'app/js/canvas-renderer.js').read_text().replace(
                '  render(scene, camera) {', '  render(scene, camera) { throw new Error("injected first frame bug");').encode()
        if data is not None:
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript' if path.endswith('.js') else 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()


class ChromeStartupTests(unittest.TestCase):
    def test_startup_scenarios(self):
        chrome = shutil.which('google-chrome')
        if not chrome:
            self.skipTest('Google Chrome is not installed')
        scenarios = {
            'normal': '模型就绪 ·',
            'fallback': '模型就绪 · Canvas 降级（性能和效果受限）',
            'rendererBug': '三维渲染初始化异常 · WEBGL_INIT',
            'frameBug': '场景渲染异常 · RENDER_FRAME',
            'config404': '模型配置加载失败 · MODEL_CONFIG',
            'asset404': '模型网格加载失败 · MODEL_ASSET',
            'invalidJSON': '模型配置加载失败 · MODEL_CONFIG',
            'invalidSTL': '模型网格解析失败 · MODEL_PARSE',
            'module404': '应用模块加载失败 · MODULE_LOAD',
            'file': '打开方式不正确 · FILE_PROTOCOL',
        }
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(FixtureHandler, directory=str(ROOT / 'app')))
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            for scenario, expected in scenarios.items():
                with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(prefix='s1-chrome-') as profile:
                    server.scenario = scenario
                    url = ((ROOT / 'app/index.html').as_uri() if scenario == 'file' else
                           f'http://127.0.0.1:{server.server_port}/')
                    command = [chrome, '--headless', f'--user-data-dir={profile}', '--no-first-run',
                               '--no-default-browser-check', '--disable-dev-shm-usage',
                               '--use-angle=swiftshader',
                               '--window-size=1440,960', '--virtual-time-budget=5000', '--dump-dom']
                    if scenario in ('fallback', 'file'):
                        command.append(f'--screenshot={ROOT / "artifacts/screenshots" / (scenario + "-diagnostic.png")}')
                    process = subprocess.Popen(command + [url], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, start_new_session=True)
                    try:
                        stdout, stderr = process.communicate(timeout=35)
                    finally:
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                    self.assertEqual(result.returncode, 0, result.stderr[-2000:])
                    self.assertIn(expected, result.stdout)
                    self.assertNotIn('使用支持 WebGL 的浏览器', result.stdout)
                    if scenario in ('config404', 'asset404'):
                        self.assertIn('HTTP 404', result.stdout)
                    if scenario == 'rendererBug':
                        self.assertIn('injected renderer bug', result.stdout)
                    if scenario == 'frameBug':
                        self.assertIn('injected first frame bug', result.stdout)
                        self.assertNotIn('模型就绪 ·', result.stdout)
                    if scenario == 'fallback':
                        self.assertIn('复杂模型可能更卡顿', result.stdout)
                    print(f'Chrome {scenario}: passed', flush=True)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
