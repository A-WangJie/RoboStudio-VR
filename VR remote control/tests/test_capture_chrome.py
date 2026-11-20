"""Real browser: teaching capture works without a Quest and uses saved config."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[2]
HTML='''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/vr-ui/panels.css"><main style="width:330px"></main><pre id="test-result" hidden></pre><script type="module">
import {createVRPages} from '/vr-ui/panels.js';
import {defaultArmConfig} from '/js/arm-config-model.js';
const config=defaultArmConfig();config.connection.layout='single';config.teaching.pairs[0].leader.device='can2';
window.s1Desktop={armConfig:async()=>({config})};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const until=async f=>{for(let i=0;i<70;i++){if(f())return;await wait(100)}throw Error('timeout')};
const assert=(v,m)=>{if(!v)throw Error(m)};
try{
 const root=createVRPages().get('capture-session').root;document.querySelector('main').append(root);const q=s=>root.querySelector(s);
 await until(()=>!q('#capture-source').disabled);
 assert(q('#capture-start').disabled,'VR requires live input');
 q('#capture-source').value='teaching-sdk';q('#capture-source').dispatchEvent(new Event('change'));
 await until(()=>!q('#capture-start').disabled);
 assert(!q('#capture-teaching').hidden,'teaching details shown');
 q('#capture-task').value='关节测试';q('#capture-start').click();
 await until(()=>q('#capture-stop').disabled===false);
 const calls=await(await fetch('/requests')).json();
 assert(calls[0].body.source==='teaching-sdk'&&calls[0].body.devices.join()==='can2','saved SDK source and interface');
 assert(calls[0].body.task==='关节测试'&&calls[0].body.rateHz===30,'task and configured sample rate');
 assert(q('#capture-source').disabled,'source locked during capture');
 q('#capture-stop').click();await until(()=>!q('#capture-start').disabled);
 assert(q('[data-v="file"]').textContent.includes('/recordings/'),'new save directory');
 document.querySelector('#test-result').textContent=JSON.stringify({ok:true,checks:['无需 VR 在线','读取保存配置','采集时锁定来源','结束采集','新保存目录']});
}catch(e){document.querySelector('#test-result').textContent=JSON.stringify({ok:false,error:e.stack})}
</script>'''

class CaptureChromeTests(unittest.TestCase):
    def test_teaching_capture(self):
        if not (ROOT/'app').is_dir():self.skipTest('DK integration checkout required')
        chrome=shutil.which('google-chrome')
        node=Path(os.environ.get('NODE_BINARY') or shutil.which('node') or str(Path.home()/'.local/opt/chatgpt/resources/cua_node/bin/node'))
        if not chrome or not node.exists():self.skipTest('Chrome / Node unavailable')
        requests=[]
        state=dict(status='disconnected',simulation={},connection={},recording={},wearMode={},teaching={},recordingDirectory=str(ROOT/'recordings'))
        class Handler(BaseHTTPRequestHandler):
            def respond(self,data,kind='application/json'):
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_GET(self):
                if self.path=='/':self.respond(HTML.encode(),'text/html; charset=utf-8')
                elif self.path=='/api/vr-bridge/state':self.respond(json.dumps(state).encode())
                elif self.path=='/requests':self.respond(json.dumps(requests).encode())
                elif self.path.startswith('/js/'):
                    self.respond((ROOT/'app'/self.path.lstrip('/')).read_bytes(),'text/javascript')
                elif self.path.startswith('/vr-ui/'):
                    path=ROOT/'VR remote control/ui'/self.path.rsplit('/',1)[1]
                    self.respond(path.read_bytes(),'text/javascript' if path.suffix=='.js' else 'text/css')
                else:self.send_error(404)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(dict(path=self.path,body=body))
                state['recording']=dict(active=self.path.endswith('/start'),source='teaching-sdk',frames=1,file=str(ROOT/'recordings/test.jsonl'))
                self.respond(b'{}')
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                (ROOT/'VR remote control/artifacts/reports').mkdir(parents=True,exist_ok=True)
                (ROOT/'VR remote control/artifacts/screenshots').mkdir(parents=True,exist_ok=True)
                report=ROOT/'VR remote control/artifacts/reports/capture-chrome.json'
                run=subprocess.run([str(node),str(ROOT/'tests/chrome-driver.cjs'),chrome,profile,f'http://127.0.0.1:{http.server_port}/',str(ROOT/'VR remote control/artifacts/screenshots/capture-chrome.png'),str(report)],capture_output=True,text=True,timeout=55)
                self.assertEqual(run.returncode,0,run.stderr)
                result=json.loads(report.read_text());self.assertTrue(result['ok'],result)
        finally:http.shutdown();http.server_close()
