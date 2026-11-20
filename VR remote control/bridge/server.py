"""Quest telemetry and explicit VR commands routed to the local RS service."""
import asyncio
import json
import math
import sys
from pathlib import Path
# Support both the existing script entry and python -m bridge.server.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import time
import threading
import os
import signal
from urllib.parse import urlsplit, parse_qs
from recording import Recorder
from teaching_capture import TeachingCapture
from connection import Connection
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/python'))
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from mapping import Mapping
from simulation_link import SimulationLink
from wear_mode import WearMode
from client_setup import ClientSetup


from protocol import validate
from paths import config_dir, recordings_dir


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.connected = False
        self.packet = None
        self.received = 0
        self.count = 0
        self.error = ''
        self.arrival_interval_ms = 0.
        self.extra_delay_ms = 0.
        self.minimum_clock_offset_ms = None
        self.mapping = Mapping()

    def snapshot(self):
        with self.lock:
            age = (time.monotonic() - self.received) * 1000 if self.packet else None
            status = 'disconnected' if not self.connected else ('waiting' if age is None else ('stale' if age > 500 else 'live'))
            if status != 'live':
                self.mapping.update(None, False, time.monotonic())
            return dict(status=status, ageMs=age, count=self.count, error=self.error, packet=self.packet, mapping=self.mapping.snapshot(),
                        network=dict(arrivalIntervalMs=round(self.arrival_interval_ms, 1),
                                     extraDelayMs=round(self.extra_delay_ms, 1)))

state = State()
simulation = SimulationLink(state)
wear_mode = WearMode(simulation.disable, mode=lambda: connection.mode, config=config_dir()/'wireless-adb.json')
connection = Connection(config_dir()/'connection.json')
recorder = Recorder(recordings_dir())
teaching = TeachingCapture(recorder)
capture_lock = threading.RLock()
task_name = ''
producer = None
bridge_loop = None

def control(action, options=None):
    options = options or {}
    if simulation.hardware_status().get('selected'):
        if action not in ('follow','stop','zero','grasp'):raise ValueError('未知 RoboData 操作')
        return simulation.hardware_command(action)
    if action == 'follow':
        simulation.enable(options.get('orientation', simulation.orientation_enabled), options.get('gripper', simulation.gripper_enabled), options.get('positionGain', simulation.telemetry.mapping.position_gain if hasattr(simulation.telemetry.mapping,'position_gain') else 1.))
    elif action == 'stop': simulation.disable()
    elif action == 'zero':
        simulation.mode_command('vr_exit')
    elif action == 'grasp': simulation.mode_command('reset' if simulation.mode_state.get('vr_mode') else 'vr_enter')
    else: raise ValueError('未知 RoboData 操作')
    return simulation.snapshot()

def record_start(options):
    with capture_lock:
        rs_task = options.get('task', '')
        if not isinstance(rs_task, str) or len(rs_task) > 80:
            raise ValueError('任务名最长 80 字')
        source = options.get('source', 'vr')
        if source == 'teaching-sdk':
            return teaching.start(rs_task.strip(), options)
        if source != 'vr': raise ValueError('未知采集来源')
        if teaching.snapshot()['status'] == 'reading': raise ValueError('示教 SDK 正在采集')
        snap=state.snapshot()
        if snap['status'] != 'live': raise ValueError('需要实时输入才能开始采集')
        return recorder.start(rs_task.strip() or task_name.strip(), dict(source=snap['packet']['source'], transport=connection.mode,
            simulationOnly=not simulation.hardware_state.get('active'),
            execution='hardware' if simulation.hardware_state.get('active') else 'simulation',robot='S1 V1', tcpReference='model-un-calibrated'))

def record_stop(reason='operator'):
    with capture_lock:
        teaching.stop(reason)
        return recorder.stop(reason)

def stop_vr_recording(reason):
    with recorder.lock:
        if recorder.snapshot().get('source') != 'teaching-sdk': recorder.stop(reason)

async def disconnect_producer():
    if producer: await producer.close(1000, 'Connection mode changed; reconnect')


def disconnect_for_setup():
    if bridge_loop:
        asyncio.run_coroutine_threadsafe(disconnect_producer(), bridge_loop).result(timeout=3)


class VRRecording:
    def stop(self, reason): stop_vr_recording(reason)

client_setup = ClientSetup(connection, wear_mode, simulation, VRRecording(), disconnect_for_setup)


async def receive(ws):
    global task_name, producer
    route=urlsplit(ws.request.path)
    if route.path != '/input':
        await ws.close(1008, 'Use /input')
        return
    if ws.request.headers.get('Origin'):
        await ws.close(1008,'Native RoboData clients only'); return
    token=parse_qs(route.query).get('token',[''])[0]
    if not connection.permits(ws.remote_address[0], token):
        await ws.close(1008, 'Select transport and check pairing code'); return
    with state.lock:
        busy = state.connected
        if not busy:
            state.mapping.update(None, False, time.monotonic())
            state.connected = True
            state.packet = None
            state.received = time.monotonic()
            state.count = 0
            state.error = ''
            state.minimum_clock_offset_ms = None
            state.arrival_interval_ms = state.extra_delay_ms = 0.
    if busy:
        await ws.close(1008, 'One producer allowed')
        return
    producer=ws
    task_name=""
    seq, stamp = -1, -1
    async def report_status():
        # Never hold up input while IK owns SimulationLink.lock or a peer reads slowly.
        while True:
            snap = state.snapshot()
            if snap['packet']:
                sim = await asyncio.to_thread(simulation.snapshot)
                rec = await asyncio.to_thread(recorder.snapshot)
                await ws.send(json.dumps(dict(type='status',echoTimeMs=snap['packet']['timeMs'],
                    simulation=sim, recording=rec, taskName=task_name, mode=connection.mode,
                    inputLive=snap['status']=='live', armMode=('real' if sim.get('execution')=='hardware' else 'simulation') if sim.get('online') else 'disconnected',
                    network=snap['network']), allow_nan=False))
            await asyncio.sleep(.2)

    def recording_frame(p, mapping):
        # Source check and append are atomic with respect to stop/start.
        with recorder.lock:
            if not recorder.snapshot()['active'] or recorder.snapshot().get('source') == 'teaching-sdk': return
            sim_state=dict(simulation.mode_state)
            sim_state['sampledAtMs']=getattr(simulation,'mode_received_ms',None)
            recorder.frame(p,sim_state,mapping)
    async def watchdog():
        while True:
            await asyncio.sleep(1)
            with state.lock: overdue=time.monotonic()-state.received > 3
            if overdue:
                await ws.close(1001,'Telemetry timed out');return
    monitor=asyncio.create_task(watchdog())
    reporter=asyncio.create_task(report_status())
    try:
        async for raw in ws:
            try:
                message=json.loads(raw)
                if not connection.permits(ws.remote_address[0], token):
                    await ws.close(1008,'Transport changed'); break
                if isinstance(message,dict) and message.get('type') == 'latencyProbe':
                    probe_id=message.get('probeId')
                    if type(probe_id) is not int or not 0 <= probe_id <= 2**63-1:
                        raise ValueError('probeId')
                    await ws.send(json.dumps(dict(type='latencyResult',probeId=probe_id)))
                    continue
                if isinstance(message,dict) and message.get('type') == 'command':
                    command_id=message.get('id','')
                    try:
                        result=await asyncio.to_thread(control,message.get('action'),message.get('options'))
                        await ws.send(json.dumps(dict(type='commandResult',id=command_id,ok=True,message=result['message'])))
                    except Exception as error:
                        await ws.send(json.dumps(dict(type='commandResult',id=command_id,ok=False,message=str(error))))
                    continue
                p = validate(message)
                name=p.get('taskName','')
                if not isinstance(name,str) or len(name)>80: raise ValueError('taskName length')
                task_name=name
                if p['seq'] <= seq or p['timeMs'] < stamp:
                    raise ValueError('out-of-order packet')
                seq, stamp = p['seq'], p['timeMs']
                with state.lock:
                    if state.received and time.monotonic() - state.received > .5:
                        state.mapping.update(None, False, time.monotonic())
                    mapped=p
                    if p.get('uiInteracting'): mapped=dict(p,right=dict(p['right'],grip=0.))
                    state.mapping.update(mapped, True, time.monotonic())
                    now = time.monotonic()
                    state.arrival_interval_ms = (now-state.received)*1000 if state.packet else 0.
                    offset = now*1000-p['timeMs']
                    if state.minimum_clock_offset_ms is None or offset < state.minimum_clock_offset_ms:
                        state.minimum_clock_offset_ms = offset
                    # Relative to the best observed transit time, NOT one-way latency.
                    state.extra_delay_ms = max(0., offset-state.minimum_clock_offset_ms)
                    state.packet = p
                    state.received = now
                    state.count += 1
                    state.error = ''
                if recorder.info['active']:
                    await asyncio.to_thread(recording_frame,p,state.snapshot()['mapping'])
            except (ValueError, TypeError, KeyError) as e:
                with state.lock:
                    state.error = str(e)
                    state.mapping.update(None, False, time.monotonic())
    except ConnectionClosed:
        pass
    finally:
        monitor.cancel()
        reporter.cancel()
        await asyncio.gather(monitor, reporter, return_exceptions=True)
        producer=None
        simulation.disable('RoboData 已断开 · 跟随停止')
        stop_vr_recording('producer_disconnected')
        with state.lock:
            state.connected = False
            state.mapping.update(None, False, time.monotonic())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/api/telemetry':
            data=json.dumps(state.snapshot(),allow_nan=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if self.path == '/api/state':
            if self.headers.get('X-Simulation-Port'):
                try: simulation.bind_port(int(self.headers['X-Simulation-Port']))
                except ValueError: pass
            snapshot = state.snapshot()
            snapshot['simulation'] = simulation.snapshot(touch=True)
            snapshot['wearMode'] = wear_mode.snapshot()
            snapshot['connection'] = connection.snapshot()
            snapshot['recording'] = recorder.snapshot()
            snapshot['recordingDirectory'] = str(recorder.directory)
            snapshot['teaching'] = teaching.snapshot()
            snapshot['taskName'] = task_name
            data = json.dumps(snapshot, allow_nan=False).encode()
            kind = 'application/json'
        elif self.path in ('/', '/index.html'):
            data = Path(__file__).with_name('index.html').read_bytes()
            kind = 'text/html; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        if self.path not in ('/api/simulation/enable', '/api/simulation/disable', '/api/wear-mode', '/api/vr/enter', '/api/vr/reset', '/api/vr/exit', '/api/connection', '/api/recording/start', '/api/recording/stop', '/api/client/configure', '/api/wireless-adb'):
            self.send_error(404)
            return
        if self.headers.get('Origin') != 'http://127.0.0.1:8767':
            self.send_error(403)
            return
        try:
            setup_result = None
            if self.headers.get('X-Simulation-Port') and self.path != '/api/wear-mode':
                simulation.bind_port(int(self.headers['X-Simulation-Port']))
            if self.path in ('/api/connection','/api/recording/start','/api/recording/stop', '/api/client/configure', '/api/wireless-adb'):
                length=int(self.headers.get('Content-Length','0'))
                if not 0 <= length <= 1024: raise ValueError('请求长度无效')
                options=json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(options,dict): raise ValueError('需要 JSON 对象')
                if self.path == '/api/wireless-adb':
                    wear_mode.configure_wireless(options)
                elif self.path == '/api/connection':
                    mode=options.get('mode')
                    if mode not in ('usb','wifi'): raise ValueError('连接方式无效')
                    simulation.disable('连接方式切换 · 已停止跟随')
                    stop_vr_recording('transport_changed')
                    connection.set(mode)
                    if bridge_loop: asyncio.run_coroutine_threadsafe(disconnect_producer(),bridge_loop).result(timeout=3)
                    if mode == 'usb': wear_mode.adb('reverse','tcp:8766','tcp:8766')
                elif self.path == '/api/client/configure':
                    setup_result = client_setup.configure(options)
                elif self.path.endswith('/start'): record_start(options)
                else: record_stop()
            elif self.path.startswith('/api/vr/'):
                simulation.mode_command({'enter':'vr_enter','reset':'reset','exit':'vr_exit'}[self.path.rsplit('/',1)[1]])
            elif self.path == '/api/wear-mode':
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024: raise ValueError('请求长度无效')
                options = json.loads(self.rfile.read(length))
                if not isinstance(options, dict): raise ValueError('需要 JSON 对象')
                wear_mode.set(options.get('enabled'))
            elif self.path.endswith('/enable'):
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 1024: raise ValueError('请求过长')
                options = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(options, dict): raise ValueError('需要 JSON 对象')
                simulation.enable(options.get('orientation', False), options.get('gripper', False), options.get('positionGain', 1.))
            else:
                simulation.disable()
                if simulation.mode_state.get('vr_preparing'):
                    simulation.mode_command('pause')
            result, code = (setup_result if setup_result is not None else wear_mode.snapshot() if self.path in ('/api/wear-mode', '/api/wireless-adb') else simulation.snapshot()), 200
        except Exception as e:
            result, code = {'error': str(e)}, 400
        data = json.dumps(result).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


async def main():
    global bridge_loop
    bridge_loop=asyncio.get_running_loop()
    current=asyncio.current_task()
    bridge_loop.add_signal_handler(signal.SIGTERM,current.cancel)
    http = ThreadingHTTPServer(('127.0.0.1', 8767), Handler)
    if os.environ.get('ROBODATA_SKIP_ADB') != '1':
        wear_mode.restore()  # Restart returns to normal sensing; no saved opt-in.
    threading.Thread(target=http.serve_forever, daemon=True).start()
    threading.Thread(target=simulation.run, daemon=True).start()
    try:
        async with serve(receive, '0.0.0.0', 8766, max_size=16384, max_queue=4, compression=None, ping_interval=None):
            print('Quest telemetry: http://127.0.0.1:8767 | USB ws://127.0.0.1:8766/input', flush=True)
            await asyncio.Future()
    finally:
        record_stop('bridge_shutdown')
        simulation.closed.set()
        simulation.disable()
        if os.environ.get('ROBODATA_SKIP_ADB') != '1':
            wear_mode.restore()
        http.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
