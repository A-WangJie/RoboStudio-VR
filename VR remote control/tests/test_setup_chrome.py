"""Exercise the actual RS panels in Google Chrome without a Quest or live bridge."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
VR = ROOT / 'VR remote control'
HTML = '''<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="/vr-ui/panels.css">
<style>body{font-family:Arial;margin:0;background:#eee}main{width:310px}</style>
<main></main><pre id="test-result" hidden></pre><script type="module">
import {createVRPages} from '/vr-ui/panels.js';
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const assert=(value,message)=>{if(!value)throw Error(message)};
const until=async(condition)=>{for(let i=0;i<80;i++){if(condition())return;await wait(100)}throw Error('等待页面更新超时')};
try{
 const device=createVRPages().get('xr-connection').root;
 document.querySelector('main').append(device);
 const q=s=>device.querySelector(s),button=q('#vr-sync');
 await until(()=>!button.disabled);
 assert(button.textContent==='USB 一键配置','按钮名称');
 await until(()=>q('#vr-adb-host').value==='172.20.10.3');
 q('#vr-transport').value='wifi';q('#vr-transport').dispatchEvent(new Event('change'));
 button.click();assert(button.disabled,'配置期间禁止重复点击');
 await until(()=>q('.vr-feedback').textContent.includes('无线调试已配置'));
 await until(()=>q('#vr-adb-host').value==='192.168.2.134'&&!button.disabled);
 button.click();
 await until(()=>q('.vr-feedback').textContent.includes('但自由摘戴无线调试未配置成功'));
 await until(()=>!button.disabled);
 button.click();
 await until(()=>q('.vr-feedback').textContent.includes('请插入 Quest USB'));
 await until(()=>!button.disabled);
 button.click();
 await until(()=>q('.vr-feedback').textContent.includes('无线调试已配置'));
 const requests=await (await fetch('/requests')).json();
 assert(requests.length===4,'只发出一键配置请求');
 assert(requests.every(x=>x.path==='/api/vr-bridge/client/configure'&&x.body.mode==='wifi'&&x.body.host==='192.168.2.67'),'同步所选模式与主机地址');
 document.querySelector('#test-result').textContent=JSON.stringify({ok:true,checks:['一键提交所选模式','新头显地址自动回填','部分成功提示','USB缺失提示','防止重复点击']});
}catch(e){document.querySelector('#test-result').textContent=JSON.stringify({ok:false,error:e.stack})}
</script>'''


class PanelTests(unittest.TestCase):
    def test_usb_setup_panel(self):
        if not (ROOT/'app').is_dir(): self.skipTest('DK integration checkout required')
        chrome = shutil.which('google-chrome')
        node = Path(os.environ.get('NODE_BINARY') or shutil.which('node') or str(Path.home()/'.local/opt/chatgpt/resources/cua_node/bin/node'))
        if not chrome or not node.exists():
            self.skipTest('Google Chrome / Node unavailable')
        requests = []
        state = dict(status='disconnected', count=0, packet=None,
                     connection=dict(mode='usb', addresses=['192.168.2.67']),
                     simulation={}, recording={},
                     wearMode=dict(wirelessEndpoint='172.20.10.3:5555'))
        class Handler(BaseHTTPRequestHandler):
            def respond(self, data, kind='application/json', status=200):
                self.send_response(status)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path == '/': self.respond(HTML.encode(), 'text/html; charset=utf-8')
                elif self.path == '/api/vr-bridge/state': self.respond(json.dumps(state).encode())
                elif self.path == '/requests': self.respond(json.dumps(requests).encode())
                elif self.path in ('/vr-ui/panels.js', '/vr-ui/hardware.js', '/vr-ui/panels.css'):
                    name = self.path.rsplit('/', 1)[1]
                    self.respond((VR / 'ui' / name).read_bytes(), 'text/javascript' if name.endswith('.js') else 'text/css')
                else: self.send_error(404)
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(dict(path=self.path, body=body))
                state['connection']['mode'] = body['mode']
                state['wearMode'] = dict(wirelessEndpoint='192.168.2.134:5555', wirelessReady=True)
                if len(requests) == 2:
                    result = dict(synced=True, wirelessReady=False, message='RD 连接参数已同步，但自由摘戴无线调试未配置成功：测试错误')
                elif len(requests) == 3:
                    self.respond(json.dumps(dict(error='请插入 Quest USB 并允许调试')).encode(), status=400)
                    return
                else: result = dict(synced=True, wirelessReady=True, message='RD Wi-Fi 连接参数已同步，头显 IP 192.168.2.134 的无线调试已配置并验证。')
                self.respond(json.dumps(result).encode())
            def log_message(self, *args): pass
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='rs-usb-setup-') as profile:
                (ROOT/'VR remote control/artifacts/reports').mkdir(parents=True,exist_ok=True)
                (ROOT/'VR remote control/artifacts/screenshots').mkdir(parents=True,exist_ok=True)
                report = VR / 'artifacts/reports/usb-setup-chrome.json'
                screenshot = VR / 'artifacts/screenshots/usb-setup-panel-full.png'
                run = subprocess.run([str(node), str(ROOT / 'tests/chrome-driver.cjs'), chrome,
                                      profile, f'http://127.0.0.1:{http.server_port}/',
                                      str(screenshot), str(report)], capture_output=True, text=True, timeout=55)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(report.read_text())
                self.assertTrue(result['ok'], result)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == '__main__': unittest.main()
