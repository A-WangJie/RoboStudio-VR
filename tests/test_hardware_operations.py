import os
"""Motor operation validation and protocol tests: no physical CAN access."""
from copy import deepcopy
import ctypes
from functools import partial
from http.server import ThreadingHTTPServer
import http.client
import json
import math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import socket
import struct
import sys
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.s1_can import S1Can, motor_command, parse_state, state_query
from server import Handler


def configuration():
    return dict(layout='single',timeoutMs=500,arms=[dict(id=c,device=f'can{i}',bitrate=1000000,endEffector='gripper') for i,c in enumerate('AB')])


def status(node,code=0,position=32768):
    return struct.pack('=IB3x8s',0x10+node,8,bytes([(code<<4)|node,position>>8,position&255,0x80,0x07,0xff,25,26]))


class FakeTransport:
    def __init__(self,device):
        self.device=device;self.commands=[];self.closed=False;self.code=0;self.missing=[];self.fault=False;self.fail_after=False
        self.send_error=None;self.refuse=False;self.reads=0
    def read(self,nodes,timeout):
        self.reads+=1
        if self.fail_after and self.commands:raise OSError('lost bus')
        return [parse_state(status(n,8 if self.fault else self.code)) for n in nodes if n not in self.missing]
    def command(self,nodes,action):
        self.commands.append((list(nodes),action))
        if not self.refuse:self.code=1 if action=='enable' else 0
        return list(nodes),self.send_error
    def close(self):self.closed=True


class HardwareOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.info=[dict(device='can0',up=True,busState='ERROR-ACTIVE',bitrate=1000000)]
        self.transport=FakeTransport('can0');self.opens=[]
        def factory(device):self.opens.append(device);return self.transport
        self.diagnostics=HardwareDiagnostics(lambda:deepcopy(self.info),lock_path=Path(self.temp.name)/'lock')
        self.operations=HardwareOperations(self.diagnostics,factory,Path(self.temp.name)/'audit.jsonl')
        self.payload=dict(config=configuration(),armId='A',confirmed=True)

    def read(self):return self.operations.operate('read',self.payload)

    def test_read_is_explicit_complete_and_never_commands(self):
        self.assertEqual(self.opens,[])
        result=self.read()
        self.assertTrue(result['complete']);self.assertTrue(result['verified'])
        self.assertFalse(result['motionExecutionAvailable'])
        self.assertEqual(len(result['samples']),7);self.assertEqual(self.transport.commands,[])
        self.assertTrue(self.transport.closed)

    def test_enable_requires_confirmation_fresh_complete_snapshot_and_rechecks_faults(self):
        with self.assertRaisesRegex(ValueError,'先读取'):self.operations.operate('enable',self.payload)
        self.assertEqual(self.opens,[])
        self.read();self.payload['confirmed']=False
        with self.assertRaisesRegex(ValueError,'确认'):self.operations.operate('enable',self.payload)
        self.payload['confirmed']=True
        key=self.operations._key(self.payload['config']['arms'][0])
        timestamp,result=self.operations.latest[key]
        self.operations.latest[key]=(timestamp-11,result)
        with self.assertRaisesRegex(ValueError,'先读取'):self.operations.operate('enable',self.payload)
        self.read();self.transport.fault=True
        with self.assertRaisesRegex(ValueError,'复查未通过'):self.operations.operate('enable',self.payload)
        self.assertEqual(self.transport.commands,[])
        self.transport.fault=False;self.transport.missing=[7];self.read()
        with self.assertRaisesRegex(ValueError,'完整状态'):self.operations.operate('enable',self.payload)
        self.assertEqual(self.transport.commands,[])

    def test_enable_verifies_actual_feedback_and_logs(self):
        self.read();result=self.operations.operate('enable',self.payload)
        self.assertTrue(result['verified']);self.assertTrue(all(s['enabled'] for s in result['samples']))
        self.assertEqual(self.transport.commands,[(list(range(1,8)),'enable')])
        self.assertTrue(json.loads(self.operations.audit_path.read_text())['verified'])
        self.transport.commands.clear()
        result=self.operations.operate('enable',self.payload)
        self.assertEqual(result['sentNodes'],[])

    def test_disable_needs_no_prior_read_and_does_not_require_confirmation(self):
        self.transport.code=1;self.payload['confirmed']=False
        result=self.operations.operate('disable',self.payload)
        self.assertTrue(result['verified']);self.assertEqual(self.transport.commands,[(list(range(1,8)),'disable')])
        self.assertEqual(self.transport.reads,1)

    def test_partial_failed_or_unconfirmed_commands_are_not_success(self):
        self.transport.missing=[2]
        result=self.operations.operate('disable',self.payload)
        self.assertFalse(result['verified']);self.assertEqual(result['missingNodes'],[2])
        self.transport.missing=[];self.transport.code=1;self.transport.refuse=True
        result=self.operations.operate('disable',self.payload)
        self.assertFalse(result['verified']);self.assertTrue(result['complete'])
        self.transport.refuse=False;self.transport.send_error='send failed'
        self.assertFalse(self.operations.operate('disable',self.payload)['verified'])

    def test_disconnection_after_command_invalidates_cache_and_logs_unknown(self):
        self.read();self.transport.fail_after=True
        with self.assertRaisesRegex(OSError,'状态未知'):self.operations.operate('enable',self.payload)
        self.assertEqual(self.operations.latest,{})
        log=json.loads(self.operations.audit_path.read_text())
        self.assertFalse(log['verified']);self.assertEqual(log['action'],'enable');self.assertTrue(self.transport.closed)

    def test_parameter_or_interface_errors_never_open_transport(self):
        for mutate in [lambda p:p.update(armId='B'),lambda p:p.update(armId='C'),
            lambda p:p['config']['arms'][0].update(device='can0;id')]:
            payload=deepcopy(self.payload);mutate(payload)
            with self.assertRaises(ValueError):self.operations.operate('disable',payload)
        for patch_info in [dict(up=False),dict(busState='BUS-OFF'),dict(bitrate=500000)]:
            original=deepcopy(self.info);self.info[0].update(patch_info)
            with self.assertRaises(ValueError):self.operations.operate('disable',self.payload)
            self.info=original
        self.assertEqual(self.opens,[])
        self.diagnostics.lock.acquire()
        try:
            with self.assertRaises(RuntimeError):self.read()
        finally:self.diagnostics.lock.release()
        self.assertEqual(self.opens,[])

    def test_selected_arm_only_and_no_gripper_configuration(self):
        self.payload['config']['layout']='dual';self.payload['armId']='B'
        self.payload['config']['arms'][1]['endEffector']='None'
        self.info.append(dict(self.info[0],device='can1'))
        result=self.operations.operate('disable',self.payload)
        self.assertEqual(self.opens,['can1']);self.assertEqual(result['sentNodes'],list(range(1,7)))
        self.assertEqual(result['armId'],'B')

    def test_api_requires_same_origin_and_explicit_operation_payload(self):
        class Quiet(Handler):
            def log_message(self,*_):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=self.temp.name))
        server.hardware_operations=self.operations;server.hardware_diagnostics=self.diagnostics
        Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(action,origin=True):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=f'http://127.0.0.1:{server.server_port}'
            connection.request('POST',f'/api/hardware/{action}',json.dumps(self.payload),headers)
            response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result
        self.assertEqual(request('enable',False)[0],403)
        self.assertEqual(request('disable',False)[0],403);self.assertEqual(self.opens,[])
        self.assertEqual(request('read')[0],200);self.assertEqual(self.transport.commands,[])
        self.payload['confirmed']=False
        self.assertEqual(request('enable')[0],400);self.assertEqual(self.transport.commands,[])
        self.assertTrue(request('disable')[1]['verified'])


class ProtocolTests(unittest.TestCase):
    def test_exact_frames_and_strict_decoder(self):
        self.assertEqual(state_query(3),struct.pack('=IB3x8s',0x7ff,8,b'\x03\x00\xcc\x00\x00\x00\x00\x00'))
        self.assertEqual(motor_command(4,'enable'),struct.pack('=IB3x8s',4,8,b'\xff'*7+b'\xfc'))
        self.assertEqual(motor_command(7,'disable'),struct.pack('=IB3x8s',7,8,b'\xff'*7+b'\xfd'))
        for action in ['reset','zero','move']:
            with self.assertRaises(ValueError):motor_command(1,action)
        for raw,flags in [(status(1),socket.MSG_DONTROUTE),(b'',0),
            (struct.pack('=IB3x8s',0x80000011,8,b'\x01'*8),0),
            (struct.pack('=IB3x8s',0x11,8,b'\x02'*8),0),
            (struct.pack('=IB3x8s',0x11,8,b'\x01\x00\x33\x0a\x01\x00\x00\x00'),0)]:
            self.assertIsNone(parse_state(raw,flags))
        self.assertTrue(parse_state(status(1,1))['enabled'])
        self.assertTrue(parse_state(status(1,8))['fault'])
        self.assertLess(parse_state(status(7,position=40000))['positionRad'],0)

    def test_transport_sends_state_queries_only_and_discards_old_frames(self):
        class FakeSocket:
            def __init__(self,*_):self.sent=[];self.queue=[status(1,1)];self.closed=False
            def bind(self,v):pass
            def setblocking(self,v):pass
            def setsockopt(self,level,option,filters):
                assert level==socket.SOL_CAN_RAW and option==socket.CAN_RAW_FILTER
                pairs=[struct.unpack_from('=II',filters,i) for i in range(0,len(filters),8)]
                assert pairs==[(0x10+n,0xc00007ff) for n in range(1,9)]
            def recvmsg(self,_):
                if not self.queue:raise BlockingIOError()
                return self.queue.pop(0),[],0,('can0',)
            def send(self,raw):
                self.sent.append(raw);node=struct.unpack('=IB3x8s',raw)[2][0]
                self.queue.append(status(node))
            def close(self):self.closed=True
        sock=FakeSocket();clock=[0.]
        def tick(*_):clock[0]+=.01;return [],[],[]
        with patch('backend.s1_can.time.monotonic',side_effect=lambda:clock[0]),patch('backend.s1_can.select.select',side_effect=tick):
            transport=S1Can('can0',lambda *_:sock)
            result=transport.read([1,2,3],300);transport.close()
        self.assertEqual([s['node'] for s in result],[1,2,3]);self.assertFalse(result[0]['enabled'])
        self.assertEqual(sock.sent,[state_query(n) for n in [1,2,3]]);self.assertTrue(sock.closed)

    def test_disable_attempts_remaining_nodes_after_a_send_failure(self):
        class FakeSocket:
            def __init__(self):self.attempted=[]
            def send(self,raw):
                node=struct.unpack('=IB3x8s',raw)[0];self.attempted.append(node)
                if node==2:raise OSError('send failed')
        transport=object.__new__(S1Can);transport.socket=FakeSocket()
        with patch('backend.s1_can.time.sleep'):
            sent,error=transport.command([1,2,3],'disable')
        self.assertEqual(transport.socket.attempted,[1,2,3]);self.assertEqual(sent,[1,3]);self.assertIn('节点 2',error)
        transport.socket=FakeSocket()
        with patch('backend.s1_can.time.sleep'):
            sent,error=transport.command([1,2,3],'enable')
        self.assertEqual(transport.socket.attempted,[1,2]);self.assertEqual(sent,[1])

    def test_read_retries_only_missing_status_within_original_deadline(self):
        for unavailable in (False,True):
            with self.subTest(unavailable=unavailable):
                clock=[0.]
                class LossySocket:
                    def __init__(self):self.sent=[];self.queue=[];self.counts={}
                    def recvmsg(self,_):
                        if not self.queue:raise BlockingIOError()
                        return self.queue.pop(0),[],0,('can0',)
                    def send(self,raw):
                        node=struct.unpack('=IB3x8s',raw)[2][0]
                        self.sent.append(raw);self.counts[node]=self.counts.get(node,0)+1
                        if node==3 and self.counts[node]==1:return
                        if node==7 and unavailable:return
                        self.queue.append(status(node))
                transport=object.__new__(S1Can);transport.socket=LossySocket()
                def wait(read,write,error,timeout):
                    clock[0]+=timeout
                    return [],[],[]
                with patch('backend.s1_can.time.monotonic',side_effect=lambda:clock[0]),patch('backend.s1_can.select.select',side_effect=wait):
                    samples=transport.read(list(range(1,8)),180,interval=.002)
                self.assertEqual([s['node'] for s in samples],list(range(1,7 if unavailable else 8)))
                self.assertLessEqual(clock[0],.180001)
                self.assertEqual(transport.socket.counts[3],2)
                self.assertEqual(transport.socket.counts[7],3 if unavailable else 1)
                for n in (1,2,4,5,6):self.assertEqual(transport.socket.counts[n],1)
                self.assertTrue(all(raw==state_query(struct.unpack('=IB3x8s',raw)[2][0]) for raw in transport.socket.sent))

    def test_decoder_matches_native_sdk_offline(self):
        """Only damiao value objects; no transport/middleware/arm construction."""
        hardware=Path(os.environ.get('ROBODATA_S1_SDK', str(ROOT.parent/'14-DOF robotic arm/S1_SDK_V2')))/'src/S1_SDK/hardware'
        if sys.version_info[:2]!=(3,10) or not hardware.exists():self.skipTest('Installed SDK oracle unavailable')
        sys.path.insert(0,str(hardware))
        from S1_SDK.hardware import motor_interface
        lib=ctypes.CDLL(motor_interface.__file__)
        ctor=getattr(lib,'_ZN6damiaoC1Ejj');ctor.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        process=getattr(lib,'_ZN6damiao7processE10frame_data');process.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint32]
        for node in range(1,8):
            for code in (0,1,8):
                obj=ctypes.create_string_buffer(64);ctor(obj,node,1)
                struct.pack_into('I',obj,36,2)  # SDK feedback parsing phase; no I/O.
                raw=status(node,code,35000);data=struct.unpack('=IB3x8s',raw)[2]
                native=struct.pack('=I8s',node,data)
                process(obj,int.from_bytes(native[:8],'little'),int.from_bytes(native[8:],'little'))
                decoded=parse_state(raw)
                actual=struct.unpack_from('5f',obj.raw,16)
                for value,expected in zip([decoded['positionRad'],decoded['velocityRadS'],decoded['torqueNm'],decoded['mosTemperatureC'],decoded['coilTemperatureC']],actual):
                    self.assertAlmostEqual(value,expected,places=4)
                self.assertEqual(decoded['enabled'],bool(obj.raw[40]))

    def test_command_frames_match_native_sdk_without_any_transport(self):
        hardware=Path(os.environ.get('ROBODATA_S1_SDK', str(ROOT.parent/'14-DOF robotic arm/S1_SDK_V2')))/'src/S1_SDK/hardware'
        if sys.version_info[:2]!=(3,10) or not hardware.exists():self.skipTest('Installed SDK oracle unavailable')
        sys.path.insert(0,str(hardware))
        from S1_SDK.hardware import motor_interface
        lib=ctypes.CDLL(motor_interface.__file__)
        ctor=getattr(lib,'_ZN6damiaoC1Ejj');ctor.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        delete=getattr(lib,'_ZdlPv');delete.argtypes=[ctypes.c_void_p]
        for node in range(1,8):
            for name,expected,enabled in [('_ZN6damiao20refresh_motor_statusEv',state_query(node),False),
                ('_ZN6damiao6enableEv',motor_command(node,'enable'),False),
                ('_ZN6damiao7disableEv',motor_command(node,'disable'),True)]:
                obj=ctypes.create_string_buffer(64);ctor(obj,node,1);obj[40]=bytes([int(enabled)])
                vector=ctypes.create_string_buffer(24)
                function=getattr(lib,name);function.argtypes=[ctypes.c_void_p,ctypes.c_void_p];function(vector,obj)
                begin,end,_=struct.unpack('PPP',vector.raw)
                try:
                    self.assertEqual(end-begin,12)
                    can_id,payload=struct.unpack('=I8s',ctypes.string_at(begin,12))
                    self.assertEqual(struct.pack('=IB3x8s',can_id,8,payload),expected)
                finally:delete(begin)


if __name__=='__main__':unittest.main()
