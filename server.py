"""Local S1 Studio, MuJoCo API and explicit non-motion CAN diagnostics."""
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import os
import signal
import threading
import time
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent / 'VR remote control'))
from bridge_service import BridgeService
from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.paths import config_dir

bridge_service = BridgeService()
hardware_diagnostics = HardwareDiagnostics()
hardware_operations = HardwareOperations(hardware_diagnostics)
motion_creation_lock = threading.RLock()


class Handler(SimpleHTTPRequestHandler):
    def vr_hardware(self):
        with motion_creation_lock:
            if not hasattr(self.server,'vr_hardware'):
                from hardware_control import VRHardwareControl
                self.server.vr_hardware=VRHardwareControl(self.motion())
        return self.server.vr_hardware

    def motion(self):
        # One controller per local server, including isolated test servers.
        with motion_creation_lock:
            if not hasattr(self.server,'hardware_motion'):
                from backend.hardware_motion import HardwareMotion
                self.server.hardware_motion=HardwareMotion(
                    getattr(self.server,'hardware_operations',hardware_operations),self.server.simulation,
                    getattr(self.server,'arm_config_path',None))
        return self.server.hardware_motion

    def log_request(self, code='-', size='-'):
        if code == 200 and self.path in ('/api/sim/state', '/api/sim/command', '/api/kinematics/fk', '/api/vr-bridge/state', '/api/hardware/interfaces','/api/hardware/mouse/state','/api/hardware/mouse/input','/api/hardware/vr/state','/api/hardware/vr/touch'):
            return
        super().log_request(code, size)

    def json_response(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def simulation(self):
        simulation = getattr(self.server, 'simulation', None)
        if simulation is None:
            self.json_response(503, {'error': 'SIM_UNAVAILABLE', 'message': getattr(self.server, 'simulation_error', 'MuJoCo 后端未启动')})
        return simulation

    def vr_proxy(self, post=False):
        action = self.path.removeprefix('/api/vr-bridge/')
        allowed = {'state'} if not post else {'setup','wear-mode','vr/enter','vr/reset','vr/exit','simulation/enable','simulation/disable','connection','recording/start','recording/stop','client/configure','wireless-adb'}
        if action not in allowed:
            self.json_response(404, {'error':'未知 VR 接口'}); return
        try:
            body = None
            if post:
                origin = self.headers.get('Origin')
                if origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                    self.json_response(403, {'error':'仅允许本机工作台操作'}); return
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 1024: raise ValueError('请求长度无效')
                body = self.rfile.read(length)
                if action == 'setup':
                    self.json_response(200, bridge_service.setup()); return
            req = Request('http://127.0.0.1:8767/api/'+action, data=body,
                headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8767',
                         'X-Simulation-Port':str(self.server.server_port)})
            with urlopen(req, timeout=(60 if action == 'client/configure' else 28) if post else 1) as r:
                self.json_response(r.status,json.load(r))
        except HTTPError as e:
            self.json_response(e.code,json.load(e))
        except Exception as e:
            self.json_response(503, {'error':'VR 桥接服务不可用：'+str(e)})

    def do_GET(self):
        if self.path=='/api/hardware/vr/state':
            if self.simulation() is None:return
            self.json_response(200,self.vr_hardware().state());return
        if self.path in ('/api/hardware/mouse/settings','/api/hardware/mouse/state'):
            if self.simulation() is None:return
            try:
                motion=self.motion()
                self.json_response(200,motion.settings() if self.path.endswith('/settings') else motion.state())
            except Exception as error:self.json_response(503,{'message':str(error)})
            return
        if self.path == '/api/hardware/interfaces':
            try:
                service = getattr(self.server, 'hardware_diagnostics', hardware_diagnostics)
                self.json_response(200, service.interfaces())
            except Exception as error:
                self.json_response(503, {'message':'无法读取 CAN 接口：'+str(error)})
            return
        if self.path.startswith('/api/vr-bridge/'):
            self.vr_proxy(); return
        if self.path in ('/vr-ui/panels.js','/vr-ui/panels.css','/vr-ui/hardware.js'):
            file = Path(__file__).resolve().parent / 'VR remote control/ui' / self.path.rsplit('/',1)[1]
            data = file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','text/javascript' if file.suffix == '.js' else 'text/css')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data); return

        if self.path == '/api/sim/state':
            simulation = self.simulation()
            if simulation:
                self.json_response(200, simulation.state())
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/hardware/vr/'):
            if self.headers.get('Origin') not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                self.json_response(403,{'message':'真机 VR 仅允许本机工作台操作'});return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.json_response(415,{'message':'需要 JSON 参数'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:raise ValueError('参数长度无效')
                value=json.loads(self.rfile.read(length))
                if not isinstance(value,dict):raise ValueError('需要 JSON 对象')
                if self.simulation() is None:return
                vr=self.vr_hardware();action=self.path.rsplit('/',1)[1]
                if action=='start':result=vr.start(value)
                elif action=='touch':result=vr.touch(value)
                elif action=='command':result=vr.command(value.get('action'),value.get('options'))
                elif action=='stop':result=vr.stop()
                elif action=='simulation':result=vr.choose_simulation()
                else:raise ValueError('未知真机 VR 操作')
                self.json_response(200,result)
            except ValueError as error:self.json_response(400,{'message':str(error)})
            except RuntimeError as error:self.json_response(409,{'message':str(error)})
            except Exception as error:self.json_response(503,{'message':str(error)})
            return
        if self.path.startswith('/api/hardware/mouse/'):
            if self.headers.get('Origin') not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                self.json_response(403,{'message':'真机控制仅允许本机工作台请求'});return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.json_response(415,{'message':'需要 JSON 参数'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:raise ValueError('控制参数长度无效')
                value=json.loads(self.rfile.read(length))
                if self.simulation() is None:return
                motion=self.motion()
                action=self.path.rsplit('/',1)[1]
                if action in ('input','start') and motion.active and motion.owner!='mouse':
                    raise ValueError('真机已被 VR 接管，请先停止 VR 控制')
                if action=='start':result=motion.start(value)
                elif action=='input':result=motion.input(value)
                elif action=='stop':
                    vr=getattr(self.server,'vr_hardware',None)
                    if vr and vr.active:vr.stop('用户停止了真机控制')
                    result=motion.stop()
                else:raise ValueError('未知真机鼠标操作')
                self.json_response(200,result)
            except ValueError as error:
                self.json_response(400,{'message':str(error),'contacts':getattr(error,'contacts',[])})
            except RuntimeError as error:self.json_response(409,{'message':str(error)})
            except Exception as error:self.json_response(503,{'message':'真机鼠标控制失败：'+str(error)})
            return
        if self.path in ('/api/hardware/detect','/api/hardware/read','/api/hardware/enable','/api/hardware/disable'):
            if self.headers.get('Origin') not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                self.json_response(403, {'message':'真机操作仅允许本机工作台请求'}); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.json_response(415, {'message':'真机操作参数需要 application/json'}); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096: raise ValueError('检测参数长度无效')
                value = json.loads(self.rfile.read(length))
                service = getattr(self.server, 'hardware_diagnostics', hardware_diagnostics)
                if self.path.endswith('/detect'):
                    result=service.detect(value)
                else:
                    motion=getattr(self.server,'hardware_motion',None)
                    if motion and motion.active and self.path.endswith('/disable'):
                        vr=getattr(self.server,'vr_hardware',None)
                        if vr and vr.active:vr.stop('用户执行失能，已停止 VR 控制')
                        motion.stop('用户执行失能，已先撤销鼠标跟随',hold=False)
                    operations=getattr(self.server,'hardware_operations',hardware_operations)
                    result=operations.operate(self.path.rsplit('/',1)[1],value)
                self.json_response(200, result)
            except ValueError as error:
                self.json_response(400, {'message':str(error)})
            except RuntimeError as error:
                self.json_response(409, {'message':str(error)})
            except Exception as error:
                self.json_response(503, {'message':'真机操作失败：'+str(error)})
            return
        if self.path.startswith('/api/vr-bridge/'):
            motion=getattr(self.server,'hardware_motion',None)
            if motion and motion.active and self.path.rsplit('/api/vr-bridge/',1)[1] in ('vr/enter','vr/reset','vr/exit','simulation/enable'):
                self.json_response(409,{'message':'请先停止真机鼠标控制，再切换 VR 模式'});return
            self.vr_proxy(post=True); return
        if self.path in ('/api/sim/command', '/api/kinematics/fk'):
            simulation = self.simulation()
            if simulation is None:
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.json_response(415, {'error': 'INVALID_INPUT', 'message': '请求需要 application/json'})
                return
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                self.json_response(403, {'error': 'ORIGIN', 'message': '仅允许本机工作台请求'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('请求长度无效')
                payload = json.loads(self.rfile.read(length))
                motion=getattr(self.server,'hardware_motion',None)
                if self.path=='/api/sim/command' and motion and motion.active:
                    raise ValueError('真机鼠标控制已接管，请先停止再执行仿真或 VR 操作')
                if self.path == '/api/kinematics/fk':
                    result = simulation.fk(payload.get('joints'))
                else:
                    result = simulation.command(payload)
                self.json_response(200, result)
            except (ValueError, TypeError, AttributeError) as error:
                self.json_response(409 if getattr(error, 'code', '') == 'COLLISION' else 400,
                    {'error': getattr(error, 'code', 'INVALID_INPUT'), 'message': str(error),
                     'contacts': getattr(error, 'contacts', []), 'residual': getattr(error, 'residual', None)})
            except Exception as error:
                print('Simulation error:', repr(error), flush=True)
                self.json_response(500, {'error': 'SIM_ERROR', 'message': str(error)})
            return
        if self.path != '/api/client-status':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError('Invalid request length')
            status = json.loads(self.rfile.read(length))
            if status.get('browser') not in ('Chrome', 'Other') or status.get('renderer') not in ('WebGL', 'Canvas') or status.get('status') != 'ready':
                raise ValueError('Invalid client status')
        except (ValueError, TypeError, AttributeError):
            self.send_error(400)
            return
        print(f"S1 Studio client ready: browser={status['browser']}, renderer={status['renderer']}", flush=True)
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--config', type=Path, help='External simulation settings JSON')
    parser.add_argument('--desktop-parent', type=int, help='Owning desktop PID; stop when the parent exits')
    parser.add_argument('--open-browser', action='store_true', help='Open Google Chrome in a new window')
    parser.add_argument('--no-browser', action='store_false', dest='open_browser', help='Start only the local server')
    args = parser.parse_args()
    chrome = shutil.which('google-chrome') or shutil.which('google-chrome-stable')
    if args.open_browser and not chrome:
        parser.exit(1, 'Google Chrome is not installed. Install it or start with --no-browser.\n')
    handler = partial(Handler, directory=str(Path(__file__).resolve().parent / 'app'))
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    except OSError as error:
        parser.exit(1, f'Cannot start S1 Studio on port {args.port}: {error}\n')
    print(f'S1 Studio: http://127.0.0.1:{server.server_port}', flush=True)
    server.simulation = None
    settings_path = args.config or config_dir()/'settings.json'
    server.arm_config_path=settings_path.parent/'arms.json'
    try:
        from backend.simulation import Simulation
        from backend.configuration import load_settings
        server.simulation = Simulation(settings=load_settings(settings_path if settings_path.is_file() or args.config else None))
        print('MuJoCo simulation backend ready.', flush=True)
    except Exception as error:
        server.simulation_error = f'MuJoCo 后端未启动：{error}。请通过 start-studio.sh 使用已安装仿真依赖的 Python 环境。'
        print(server.simulation_error, flush=True)
    if args.desktop_parent:
        if server.simulation is None:
            server.server_close()
            parser.exit(1, server.simulation_error + '\n')
        print('S1_BACKEND_READY ' + json.dumps({'port': server.server_port, 'pid': os.getpid()}), flush=True)
        def supervise_parent():
            while True:
                if os.getppid() != args.desktop_parent:
                    server.simulation.command({'type': 'pause'})
                    server.shutdown()
                    return
                time.sleep(.5)
        threading.Thread(target=supervise_parent, daemon=True).start()
    def stop_service(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop_service)
    if args.open_browser:
        subprocess.Popen([chrome, '--new-window', f'http://127.0.0.1:{server.server_port}'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('Opened Google Chrome. Keep this terminal open while using S1 Studio.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(server,'vr_hardware'):
            server.vr_hardware.stop('工作台关闭，已停止 VR 下发')
        if hasattr(server,'hardware_motion'):
            server.hardware_motion.stop('工作台关闭，已停止鼠标下发')
        if server.simulation:
            server.simulation.close()
        server.server_close()


if __name__ == '__main__':
    main()
