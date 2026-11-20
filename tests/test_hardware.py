"""CAN diagnostics with simulated transports: tests never touch physical hardware."""
from copy import deepcopy
import fcntl
from functools import partial
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import socket
import struct
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from backend.hardware import HardwareDiagnostics, parse_ping_reply, probe_can, validate_detection
from server import Handler


def config(layout='auto'):
    return dict(layout=layout, timeoutMs=1000, arms=[dict(id=slot, device=f'can{i}',
        bitrate=1000000, endEffector='gripper') for i,slot in enumerate('AB')])


def interface(device='can0', **changes):
    return dict(dict(device=device,up=True,busState='ERROR-ACTIVE',bitrate=1000000,
        rxPackets=0,txPackets=0,rxErrors=0,txErrors=0), **changes)


def reply(node, can_flags=0, mode=1):
    return struct.pack('=IB3x8s', (0x10+node)|can_flags,8,struct.pack('<H',node)+b'\x33\x0a'+struct.pack('<I',mode))


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.inventory=[interface()]
        self.calls=[]
        self.answer=list(range(1,8))
        def probe(device,end,timeout):
            self.calls.append((device,end,timeout))
            nodes=list(range(1,8 if end=='gripper' else 7))
            return dict(requiredNodes=nodes,respondingNodes=self.answer,
                missingNodes=sorted(set(nodes)-set(self.answer)),sentNodes=nodes,elapsedMs=600)
        self.service=HardwareDiagnostics(lambda:deepcopy(self.inventory),probe,Path(self.temp.name)/'detect.lock')

    def test_validation_rejects_unsafe_or_ambiguous_settings(self):
        edits=[lambda c:c.update(layout='bad'),lambda c:c.update(timeoutMs=True),
            lambda c:c.update(timeoutMs=30001),lambda c:c.update(arms=[]),
            lambda c:c['arms'][0].update(device='can0;id'),lambda c:c['arms'][0].update(device='../can0'),
            lambda c:c['arms'][0].update(bitrate=True),lambda c:c['arms'][0].update(bitrate=0),
            lambda c:c['arms'][0].update(endEffector='other'),lambda c:c['arms'][1].update(id='A'),
            lambda c:c['arms'][1].update(device='can0')]
        for edit in edits:
            draft=config();edit(draft)
            with self.subTest(draft=draft),self.assertRaises(ValueError):validate_detection(draft)
        draft=config('single');draft['arms'][1]['device']='can0'
        self.assertEqual(validate_detection(draft),draft)

    def test_single_auto_and_dual_never_rebind_devices(self):
        result=self.service.detect(config())
        self.assertEqual([a['status'] for a in result['arms']],['online','missing_interface'])
        self.assertEqual(result['detectedCount'],1)
        self.assertFalse(result['executionAvailable']);self.assertTrue(result['stateReadingAvailable']);self.assertTrue(result['motorModeAvailable'])
        self.assertEqual(result['config'],config())
        self.inventory.append(interface('can1'))
        self.assertEqual(self.service.detect(config('dual'))['detectedCount'],2)
        self.calls.clear()
        result=self.service.detect(config('single'))
        self.assertEqual(result['arms'][1]['status'],'unused')
        self.assertEqual(len(self.calls),1)

    def test_unusable_interfaces_and_mismatched_bitrate_skip_probe(self):
        for inventory,status in [([], 'missing_interface'),([interface(up=False)],'interface_down'),
            ([interface(busState='BUS-OFF')],'bus_fault'),([interface(bitrate=500000)],'bitrate_mismatch')]:
            self.inventory=inventory
            with self.subTest(status=status):
                self.assertEqual(self.service.detect(config('single'))['arms'][0]['status'],status)
                self.assertEqual(self.calls,[])

    def test_partial_empty_and_no_gripper(self):
        self.answer=[1,2,3]
        result=self.service.detect(config('single'))['arms'][0]
        self.assertEqual(result['status'],'partial');self.assertEqual(result['missingNodes'],[4,5,6,7])
        self.answer=[]
        self.assertEqual(self.service.detect(config('single'))['arms'][0]['status'],'no_response')
        self.answer=list(range(1,7))
        draft=config('single');draft['arms'][0].update(bitrate=None,endEffector='None')
        self.assertEqual(self.service.detect(draft)['detectedCount'],1)

    def test_probe_error_and_lock_release(self):
        def fail(*_):raise OSError('interface disappeared')
        self.service.probe=fail
        self.assertEqual(self.service.detect(config('single'))['arms'][0]['status'],'probe_error')
        self.service.lock.acquire()
        with self.assertRaises(RuntimeError):self.service.detect(config())
        self.service.lock.release()
        with self.service.lock_path.open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError):self.service.detect(config())
        self.service.detect(config())
        self.assertFalse(self.service.lock.locked())

    def test_reply_requires_remote_mode_register_and_accepts_both_verified_modes(self):
        for node in range(1,9):
            for mode in (1,2):self.assertEqual(parse_ping_reply(reply(node,mode=mode)),node)
        for frame,flags in [(reply(1),socket.MSG_DONTROUTE),(b'',0),(reply(0),0),(reply(9),0),
            (reply(1,0x80000000),0),(reply(1,0x40000000),0),(reply(1,0x20000000),0),
            (reply(1,mode=0),0),(reply(1,mode=99),0),
            (struct.pack('=IB3x8s',0x11,8,b'\x02\x00\x33\x0a\x02\x00\x00\x00'),0),
            (reply(1)[:-1]+b'\x01',0),(reply(1)[:4]+b'\x07'+reply(1)[5:],0)]:
            self.assertIsNone(parse_ping_reply(frame,flags))

    def test_transport_only_sends_verified_ping_frames_and_closes(self):
        class FakeSocket:
            def __init__(self,respond=True):self.sent=[];self.queue=[];self.closed=False;self.respond=respond
            def bind(self,address):self.address=address
            def setblocking(self,value):pass
            def setsockopt(self,*args):pass
            def send(self,frame):
                self.sent.append(frame)
                if self.respond:
                    node=struct.unpack('=IB3x8s',frame)[2][0]
                    # Captured real device: joints in mode 2, gripper in mode 1.
                    self.queue.append(reply(node,mode=2 if node<=6 else 1))
            def recvmsg(self,_):
                if self.queue:return self.queue.pop(0),[],0,('can0',)
                raise BlockingIOError()
            def close(self):self.closed=True
        for respond in [True,False]:
            sock=FakeSocket(respond);clock=[0.]
            def tick(*args):clock[0]+=.02;return ([],[],[])
            with patch('backend.hardware.socket.socket',return_value=sock),patch('backend.hardware.time.monotonic',side_effect=lambda:clock[0]),patch('backend.hardware.select.select',side_effect=tick):
                result=probe_can('can0','gripper',1000)
            self.assertTrue(sock.closed);self.assertEqual(sock.address,('can0',))
            self.assertEqual(result['respondingNodes'],list(range(1,8)) if respond else [])
            self.assertEqual(sock.sent,[struct.pack('=IB3x8s',0x7ff,8,struct.pack('<H',n)+b'\x33\x0a\x00\x00\x00\x00') for n in range(1,8)])
        sock=FakeSocket()
        with patch.object(sock,'bind',side_effect=OSError('down')),patch('backend.hardware.socket.socket',return_value=sock):
            with self.assertRaises(OSError):probe_can('can0','gripper',1000)
        self.assertTrue(sock.closed)

    def test_http_origin_validation_and_injected_service(self):
        class QuietHandler(Handler):
            def log_message(self,*_):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=self.temp.name))
        server.hardware_diagnostics=self.service
        Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(origin=None,body=None,content_type='application/json',method='POST'):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            headers={'Content-Type':content_type}
            if origin:headers['Origin']=origin
            conn.request(method,'/api/hardware/detect' if method=='POST' else '/api/hardware/interfaces',
                json.dumps(config('single')) if body is None else body,headers)
            res=conn.getresponse();data=res.read();conn.close();return res.status,json.loads(data)
        origin=f'http://127.0.0.1:{server.server_port}'
        self.assertEqual(request()[0],403)
        self.assertEqual(request('http://example.com')[0],403)
        self.assertEqual(request(origin,content_type='text/plain')[0],415)
        self.assertEqual(request(origin,body='{broken')[0],400)
        self.assertEqual(request(origin,body='[]')[0],400)
        self.assertEqual(request(origin,body=' '*4097)[0],400)
        self.assertEqual(self.calls,[])
        self.assertEqual(request(method='GET')[0],200);self.assertEqual(self.calls,[])
        status,result=request(origin)
        self.assertEqual(status,200);self.assertEqual(result['detectedCount'],1)


if __name__=='__main__':unittest.main()
