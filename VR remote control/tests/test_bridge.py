import asyncio
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'bridge'))
import server
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

def packet():
    hand = dict(connected=True, tracked=True, primary=False, secondary=False, position=[0,1,0], rotation=[0,0,0,1], stick=[0,0], trigger=.5, grip=0)
    return dict(version=1, source='simulated', seq=1, timeMs=1000, focused=True, left=hand, right=copy.deepcopy(hand))

class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_usb_setup_endpoint_preserves_partial_result(self):
        from http.server import ThreadingHTTPServer
        import threading
        from unittest.mock import patch
        from urllib.request import Request, urlopen
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        expected = dict(synced=True, wirelessReady=False, message='RD 已同步，无线调试失败')
        def request():
            req = Request(f'http://127.0.0.1:{http.server_port}/api/client/configure',
                          data=b'{"mode":"wifi","host":"192.168.2.67"}',
                          headers={'Origin': 'http://127.0.0.1:8767'})
            with urlopen(req, timeout=3) as response:
                return json.load(response)
        try:
            with patch.object(server.client_setup, 'configure', return_value=expected) as configure:
                self.assertEqual(await asyncio.to_thread(request), expected)
                configure.assert_called_once_with(dict(mode='wifi', host='192.168.2.67'))
        finally:
            await asyncio.to_thread(http.shutdown)
            http.server_close()
            thread.join()

    async def test_stream_validation_stale_disconnect(self):
        server.state = server.State()
        async with serve(server.receive, '127.0.0.1', 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            async with connect(f'ws://127.0.0.1:{port}/input?token={server.connection.token}') as ws:
                p = packet()
                await ws.send(json.dumps(p)); await asyncio.sleep(.03)
                self.assertEqual(server.state.snapshot()['status'], 'live')
                await ws.send(json.dumps(p)); await asyncio.sleep(.03)
                self.assertEqual(server.state.snapshot()['count'], 1)
                self.assertIn('out-of-order', server.state.snapshot()['error'])
                await asyncio.sleep(.52)
                self.assertEqual(server.state.snapshot()['status'], 'stale')
            await asyncio.sleep(.03)
            self.assertEqual(server.state.snapshot()['status'], 'disconnected')
    async def test_slow_status_does_not_block_telemetry(self):
        import time
        from unittest.mock import patch
        server.state=server.State()
        original=server.simulation.snapshot
        def slow_snapshot(*args, **kwargs):
            time.sleep(.3)
            return original(*args, **kwargs)
        with patch.object(server.simulation,'snapshot',slow_snapshot):
            async with serve(server.receive,'127.0.0.1',0) as srv:
                port=srv.sockets[0].getsockname()[1]
                async with connect(f'ws://127.0.0.1:{port}/input?token={server.connection.token}') as ws:
                    p=packet();await ws.send(json.dumps(p))
                    await asyncio.sleep(.22)  # status worker is now waiting
                    for i in range(2,12):
                        p=packet();p['seq']=i;p['timeMs']=1000+i*30
                        await ws.send(json.dumps(p))
                    await asyncio.sleep(.05)
                    self.assertEqual(server.state.snapshot()['count'],11)
                    self.assertEqual(server.state.snapshot()['packet']['seq'],11)

    async def test_latency_probe_is_not_telemetry(self):
        server.state=server.State()
        async with serve(server.receive,'127.0.0.1',0) as srv:
            port=srv.sockets[0].getsockname()[1]
            async with connect(f'ws://127.0.0.1:{port}/input?token={server.connection.token}') as ws:
                await ws.send(json.dumps(dict(type='latencyProbe',probeId=123)))
                reply=json.loads(await asyncio.wait_for(ws.recv(),.5))
                self.assertEqual(reply,dict(type='latencyResult',probeId=123))
                self.assertEqual(server.state.snapshot()['count'],0)
                self.assertIsNone(server.state.snapshot()['packet'])
                await ws.send(json.dumps(packet()))
                await asyncio.sleep(.03)
                self.assertEqual(server.state.snapshot()['count'],1)
                self.assertEqual(server.state.snapshot()['error'],'')

    def test_reject_invalid(self):
        for key, value in [('position',[float('nan'),0,0]),('rotation',[0,0,0,0]),('trigger',2),('tracked','true')]:
            p=packet(); p['left'][key]=value
            with self.assertRaises(ValueError): server.validate(p)
        p=packet(); p['focused']=False
        with self.assertRaises(ValueError): server.validate(p)

if __name__=='__main__': unittest.main()
