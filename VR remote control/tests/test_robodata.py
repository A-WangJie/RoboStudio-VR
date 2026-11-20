import asyncio
import json
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from recording import Recorder
from connection import Connection
import server
from test_bridge import packet
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect

class RecordingTests(unittest.TestCase):
    def test_protocol_names_and_disconnect(self):
        with tempfile.TemporaryDirectory() as temp:
            r=Recorder(temp)
            a=r.start('../../抓取 test',{'source':'simulated'})
            self.assertEqual(Path(a['file']).parent,Path(temp))
            r.frame(packet(),{'revision':2},{'active':False})
            with self.assertRaises(ValueError):r.start('overlap',{})
            r.stop('producer_disconnected')
            lines=[json.loads(line) for line in Path(a['file']).read_text().splitlines()]
            self.assertEqual([l['type'] for l in lines],['header','frame','footer'])
            self.assertEqual(lines[-1]['frames'],1)
            self.assertEqual(lines[-1]['reason'],'producer_disconnected')
            self.assertFalse(r.snapshot()['active'])
    def test_wireless_requires_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Connection(Path(temp)/'config.json')
            self.assertFalse(c.permits('192.168.1.2',''))
            self.assertTrue(c.permits('127.0.0.1',''))
            c.set('wifi')
            self.assertFalse(c.permits('127.0.0.1',''))
            self.assertTrue(c.permits('192.168.1.2',c.token))
            self.assertEqual(Connection(c.path).token,c.token)

class WirelessTests(unittest.IsolatedAsyncioTestCase):
    async def test_ack_task_record_command_and_disconnect(self):
        old=(server.state,server.connection,server.recorder,server.simulation)
        with tempfile.TemporaryDirectory() as temp:
            server.state=server.State();server.connection=Connection(Path(temp)/'connection.json');server.connection.set('wifi')
            server.recorder=Recorder(Path(temp)/'records')
            class FakeSim:
                import threading
                lock=threading.RLock()
                mode_state={'revision':1}
                hardware_state={}
                enabled=True
                def hardware_status(self):return self.hardware_state
                def disable(self,*args): self.enabled=False
                def snapshot(self):return {'enabled':self.enabled,'message':'stopped'}
            server.simulation=FakeSim()
            try:
                async with serve(server.receive,'127.0.0.1',0) as srv:
                    endpoint=f'ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}/input'
                    async with connect(endpoint) as denied:
                        await denied.wait_closed(); self.assertEqual(denied.close_code,1008)
                    async with connect(endpoint+'?token='+server.connection.token) as ws:
                        p=packet();p['taskName']='VR任务'
                        await ws.send(json.dumps(p)); reply=json.loads(await ws.recv())
                        self.assertEqual(reply['taskName'],'VR任务')
                        server.record_start({'task':'  RS任务  '})
                        self.assertEqual(server.recorder.snapshot()['task'],'RS任务')
                        self.assertTrue(Path(server.recorder.snapshot()['file']).name.startswith('RS任务_'))
                        server.recorder.stop()
                        server.record_start({'task':'   '})
                        self.assertEqual(server.recorder.snapshot()['task'],'VR任务')
                        p['seq']=2;await ws.send(json.dumps(p));await asyncio.sleep(.05)
                        await ws.send(json.dumps(dict(type='command',id='stop1',action='stop')))
                        reply=json.loads(await ws.recv());self.assertTrue(reply['ok']);self.assertEqual(reply['id'],'stop1')
                    await asyncio.sleep(.05)
                    self.assertFalse(server.recorder.snapshot()['active'])
                    self.assertEqual(server.recorder.snapshot()['frames'],1)
            finally: server.state,server.connection,server.recorder,server.simulation=old
