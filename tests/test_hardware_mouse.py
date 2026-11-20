import os
"""Bounded real-arm control against simulated transports only. No CAN sockets."""
from copy import deepcopy
import ctypes
from functools import partial
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
import json
import math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import struct
import sys
import tempfile
from threading import Thread
import unittest

import numpy as np

from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.hardware_motion import HardwareMotion
from backend.s1_can import position_mode, position_velocity
from backend.simulation import Simulation, CommandError
from server import Handler


class MotionTransport:
    def __init__(self,device):
        self.device=device;self.q=[0.,.8,1.2,.6,0.,0.,1.5];self.writes=[];self.closed=False
        self.enabled=True;self.missing=False;self.failure=False;self.fault=False;self.frozen=False
    def read(self,nodes,timeout,interval=.02):
        if self.failure:raise OSError('模拟电缆拔出')
        return [dict(node=n,positionRad=self.q[n-1],positionDeg=math.degrees(self.q[n-1]),positionValid=True,
            enabled=self.enabled,stateCode=8 if self.fault else int(self.enabled),fault=self.fault,
            state='故障' if self.fault else '已使能' if self.enabled else '已失能',velocityRadS=0,torqueNm=0,
            mosTemperatureC=25,coilTemperatureC=25,receivedAtMs=1) for n in nodes if not self.missing or n!=3]
    def move(self,positions,velocity,initialize=False):
        self.writes.append((deepcopy(positions),velocity,initialize))
        if not self.frozen:
            for n,p in positions.items():self.q[n-1]=p
    def close(self):self.closed=True


class MouseHardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=[10.]
        self.info=[dict(device='can0',up=True,bitrate=1000000,busState='ERROR-ACTIVE')]
        self.transport=MotionTransport('can0')
        self.diagnostics=HardwareDiagnostics(lambda:deepcopy(self.info),lock_path=Path(self.temp.name)/'lock')
        self.operations=HardwareOperations(self.diagnostics,lambda device:self.transport,Path(self.temp.name)/'audit.jsonl')
        self.sim=Simulation(start_worker=False);self.addCleanup(self.sim.close)
        self.config=dict(layout='single',timeoutMs=500,arms=[dict(id=c,device=f'can{i}',bitrate=1000000,endEffector='gripper') for i,c in enumerate('AB')])
        self.configfile=Path(self.temp.name)/'arms.json'
        self.configfile.write_text(json.dumps(dict(connection=dict(layout='single',timeoutMs=500),arms=self.config['arms'])))
        self.motion=HardwareMotion(self.operations,self.sim,self.configfile,start_worker=False,clock=lambda:self.clock[0])
        self.addCleanup(lambda:self.motion.stop(hold=False))
        self.start_value=dict(config=self.config,armId='A',confirmed=True,speedDegS=3,gripper=None)
        self.sequence=0

    def start(self):return self.motion.start(self.start_value)
    def input(self,command=None):
        self.sequence+=1
        return self.motion.input(dict(token=self.motion.token,sequence=self.sequence,command=command))
    def tick(self,seconds=.05):
        self.clock[0]+=seconds;self.motion.tick()
    def target(self,delta=.2):
        q=self.motion.actual.copy();q[0]+=delta
        return dict(type='joints',joints=q.tolist(),gripper=self.sim.gripper)

    def test_start_requires_confirmation_saved_binding_enabled_feedback_and_no_mode_conflict(self):
        for change in [dict(confirmed=False),dict(armId='B'),dict(speedDegS=99)]:
            value=dict(self.start_value,**change)
            with self.assertRaises(ValueError):self.motion.start(value)
        wrong=deepcopy(self.start_value);wrong['config']['arms'][0]['device']='can7'
        with self.assertRaisesRegex(ValueError,'保存'):self.motion.start(wrong)
        self.transport.enabled=False
        with self.assertRaisesRegex(OSError,'失能'):self.start()
        self.transport.enabled=True;self.sim.vr_mode=True
        with self.assertRaisesRegex(ValueError,'VR'):self.start()
        self.sim.vr_mode=False;self.sim.running=True
        with self.assertRaisesRegex(ValueError,'暂停'):self.start()
        self.assertEqual(self.transport.writes,[])

    def test_takeover_aligns_only_preview_and_reserves_can_no_motion_until_mouse_input(self):
        result=self.start()
        self.assertTrue(result['active']);self.assertIn('token',result)
        np.testing.assert_allclose(result['simulation']['joints'],self.transport.q[:6])
        self.tick();self.assertEqual(self.transport.writes,[])
        with self.assertRaises(RuntimeError):self.operations.operate('read',self.start_value)
        with self.assertRaises(RuntimeError):self.start()
        self.motion.stop()
        self.assertTrue(self.transport.closed);self.assertFalse(self.motion.active)
        self.assertEqual(self.transport.writes,[])
        self.assertTrue(self.diagnostics.lock.acquire(blocking=False));self.diagnostics.lock.release()

    def test_first_and_subsequent_targets_are_speed_and_acceleration_limited(self):
        self.start();self.input(self.target(.3));initial=self.transport.q[0];previous=initial
        for _ in range(25):
            self.input();self.tick()
            positions,speed,initialize=self.transport.writes[-1]
            self.assertLessEqual(abs(positions[1]-previous),math.radians(3)*.05+1e-10)
            self.assertEqual(speed,math.radians(3));self.assertEqual(set(positions),set(range(1,7)))
            previous=positions[1]
        self.assertGreater(previous,initial)
        self.assertTrue(self.transport.writes[0][2]);self.assertFalse(self.transport.writes[-1][2])
        self.assertLess(self.transport.writes[0][0][1]-initial,math.radians(3)*.05)
        self.assertEqual(self.transport.q[6],1.5)

    def test_measured_zero_boundary_noise_does_not_prevent_small_joint_control(self):
        # Actual device's near-zero readings; run only in the fake transport.
        self.transport.q=np.radians([-4.229,.011,-.055,-.164,-4.972,-.011,86.433]).tolist()
        self.start()
        q=np.clip(self.motion.actual,self.sim.limits[:,0],self.sim.limits[:,1]);q[0]-=math.radians(1)
        self.input(dict(type='joints',joints=q.tolist(),gripper=40));self.tick()
        self.assertTrue(self.motion.active,self.motion.message)
        self.assertEqual(len(self.transport.writes),1)
        self.assertGreater(self.transport.q[0],q[0])

    def test_small_cartesian_target_is_solved_from_actual_pose(self):
        self.start();q=self.motion.actual.copy();q[0]+=.005
        pose=self.sim.fk(q)
        self.input(dict(type='pose',position=pose['position'],quaternion=pose['quaternion'],position_only=False,gripper=40))
        self.tick()
        self.assertTrue(self.motion.active,self.motion.message);self.assertTrue(self.transport.writes)
        self.assertLess(np.max(np.abs(self.motion.target-q)),math.radians(.1))

    def test_replay_wrong_token_expired_lease_and_invalid_targets_do_not_move(self):
        self.start();self.input()
        for value in [dict(token='old',sequence=2),dict(token=self.motion.token,sequence=1)]:
            with self.assertRaises(ValueError):self.motion.input(value)
        for command in [dict(type='enable'),dict(type='joints',joints=[0]*5),dict(type='joints',joints=[99]*6),
            dict(type='joints',joints=[float('nan')]*6),dict(type='joints',joints=[True]*6)]:
            with self.assertRaises(ValueError):self.input(command)
        self.assertEqual(self.transport.writes,[])
        self.tick(.8);self.assertFalse(self.motion.active);self.assertEqual(self.transport.writes,[])
        with self.assertRaises(ValueError):self.input(self.target())

    def test_watchdog_holds_recent_actual_and_never_disables_or_reenables(self):
        self.start();self.input(self.target());self.tick();self.input();self.tick()
        self.clock[0]+=.6;self.input() # renew without changing the destination
        # A final fresh status precedes loss of the browser heartbeat.
        self.tick();self.clock[0]+=.8;self.motion.tick()
        self.assertFalse(self.motion.active);self.assertIn('超时',self.motion.message)
        self.assertTrue(self.transport.enabled)
        self.assertTrue(self.transport.closed)

    def test_motor_disable_missing_fault_interface_loss_or_read_failure_stops_writes(self):
        for failure in ('disabled','missing','fault','interface','read'):
            with self.subTest(failure=failure):
                self.transport.enabled=True;self.transport.missing=False;self.transport.failure=False;self.transport.fault=False;self.info[0]['up']=True
                self.start();self.input(self.target());count=len(self.transport.writes)
                if failure=='disabled':self.transport.enabled=False
                if failure=='missing':self.transport.missing=True
                if failure=='fault':self.transport.fault=True
                if failure=='interface':self.info[0]['up']=False
                if failure=='read':self.transport.failure=True
                self.tick()
                self.assertFalse(self.motion.active);self.assertEqual(len(self.transport.writes),count)

    def test_following_error_halts_instead_of_chasing_a_blocked_arm(self):
        self.start();self.input(self.target(.3));self.transport.frozen=True
        for _ in range(80):
            if not self.motion.active:break
            self.input();self.tick()
        self.assertFalse(self.motion.active);self.assertIn('偏差超过',self.motion.message)

    def test_feedback_loss_keeps_node_details_on_next_heartbeat_and_in_audit(self):
        self.start();token=self.motion.token
        self.input(dict(type='preset',name='vr-grab'));self.tick()
        count=len(self.transport.writes)
        self.transport.missing=True;self.tick()
        self.assertFalse(self.motion.active)
        self.assertEqual(len(self.transport.writes),count)
        self.assertEqual(self.motion.state()['feedbackStatus']['missingNodes'],[3])
        reason=self.motion.message
        self.assertIn('J3（节点 3）',reason)
        with self.assertRaises(ValueError) as raised:
            self.motion.input(dict(token=token,sequence=self.sequence+1))
        self.assertEqual(str(raised.exception),reason)
        with self.assertRaisesRegex(ValueError,'会话已失效'):
            self.motion.input(dict(token='unrelated',sequence=self.sequence+2))
        self.assertEqual(self.motion.stop()['message'],reason)
        audit=json.loads(self.operations.audit_path.read_text().splitlines()[-1])
        self.assertEqual(audit['feedbackStatus']['missingNodes'],[3])
        self.assertFalse(audit['holdSent'])

    def test_saved_connection_change_revokes_control_before_next_write(self):
        self.start();self.input(self.target());count=len(self.transport.writes)
        saved=json.loads(self.configfile.read_text());saved['arms'][0]['device']='can9'
        self.configfile.write_text(json.dumps(saved));self.tick()
        self.assertFalse(self.motion.active);self.assertIn('连接配置已改变',self.motion.message)
        self.assertEqual(len(self.transport.writes),count)

    def test_hold_discards_destination_and_keeps_actual_position(self):
        self.start();self.input(self.target());self.tick();q=np.array(self.transport.q[:6])
        self.input(dict(type='hold'));self.tick();self.tick()
        np.testing.assert_allclose(self.transport.q[:6],q)

    def test_home_and_vr_grab_presets_use_shared_limits_without_switching_mode(self):
        for name,key in [('home','homeRadians'),('vr-grab','vrGrabRadians')]:
            with self.subTest(name=name):
                self.start();self.input(dict(type='preset',name=name))
                np.testing.assert_allclose(self.motion.target,self.sim.spec[key])
                self.assertEqual(self.transport.writes,[])
                self.assertFalse(self.sim.vr_mode)
                previous=np.array(self.transport.q[:6]);self.tick()
                self.assertTrue(self.motion.active,self.motion.message)
                self.assertLessEqual(np.max(np.abs(np.array(self.transport.q[:6])-previous)),math.radians(3)*.05+1e-10)
                self.assertNotIn(7,self.transport.writes[-1][0])
                self.motion.stop();self.transport.writes.clear()

    def test_calibrated_vr_preset_resets_jaw_to_40_percent_home_keeps_opening(self):
        self.start_value['gripper']=dict(closedDeg=.011,openDeg=119.459)
        self.start();opening=self.motion.target_grip
        self.input(dict(type='preset',name='home'));self.assertEqual(self.motion.target_grip,opening)
        self.input(dict(type='preset',name='vr-grab'));self.assertEqual(self.motion.target_grip,40)
        self.assertEqual(self.transport.writes,[])

    def test_applying_gripper_range_in_session_aligns_without_movement_or_old_targets(self):
        self.start();self.input(self.target());self.tick();count=len(self.transport.writes)
        result=self.input(dict(type='gripper-config',confirmed=True,gripper=dict(closedDeg=.011,openDeg=119.459)))
        self.assertTrue(result['gripperAvailable']);self.assertFalse(self.motion.has_target)
        self.assertEqual(len(self.transport.writes),count)
        self.assertAlmostEqual(result['simulation']['gripper'],(math.degrees(1.5)-.011)/(119.459-.011)*100)
        self.input();self.tick();self.assertEqual(len(self.transport.writes),count)
        self.input(dict(type='joints',joints=self.motion.actual.tolist(),gripper=40));self.tick()
        self.assertTrue(self.transport.writes[-1][2],'Newly controlled node 7 must initialize position/velocity mode')
        self.assertIn(7,self.transport.writes[-1][0])

    def test_gripper_calibration_is_bound_to_the_configured_device(self):
        path=self.configfile.parent/'gripper-calibration.json'
        path.write_text(json.dumps(dict(arms=dict(A=dict(device='can0',closedDeg=.011,openDeg=119.459)))))
        self.assertEqual(self.motion.settings()['gripperCalibrations']['A']['openDeg'],119.459)
        config=json.loads(self.configfile.read_text());config['arms'][0]['device']='can4';self.configfile.write_text(json.dumps(config))
        self.assertEqual(self.motion.settings()['gripperCalibrations'],{})

    def test_invalid_gripper_range_or_unconfirmed_configuration_never_moves(self):
        for command in [dict(type='gripper-config',confirmed=False,gripper=dict(closedDeg=0,openDeg=120)),
            dict(type='gripper-config',confirmed=True,gripper=dict(closedDeg=0,openDeg=2)),
            dict(type='gripper-config',confirmed=True,gripper=dict(closedDeg=-90,openDeg=-10)),
            dict(type='preset',name='unrecognized')]:
            self.start()
            with self.assertRaises(ValueError):self.input(command)
            self.assertFalse(self.motion.active);self.assertEqual(self.transport.writes,[])

    def test_gripper_requires_explicit_endpoints_and_uses_bounded_motor_angle(self):
        self.start();command=self.target();command['gripper']=90
        with self.assertRaisesRegex(ValueError,'夹爪行程'):self.input(command)
        self.motion.stop();self.start_value['gripper']=dict(closedDeg=0,openDeg=90)
        self.start();before=self.transport.q[6]
        command=self.target();command['gripper']=80
        self.input(command);self.tick()
        self.assertIn(7,self.transport.writes[-1][0]);self.assertLess(abs(self.transport.q[6]-before),math.radians(3)*.05)
        self.assertLess(self.transport.q[6],before)

    def test_vr_ik_retries_smaller_step_from_measured_seed(self):
        from unittest.mock import patch
        self.motion.start(self.start_value,owner='vr')
        measured=self.motion.actual.copy()
        pose=self.sim.fk(measured)
        goal=np.asarray(pose['position'])+np.array([.004,0,0])
        old_target=self.sim.target.copy();calls=[]
        def solve(position,quaternion,position_only):
            calls.append(position)
            np.testing.assert_allclose(self.sim.target,measured)
            return (measured+(.3 if len(calls)==1 else .001),{})
        with self.sim.lock,patch.object(self.sim,'_ik',side_effect=solve):
            result=self.motion._vr_pose(dict(position=goal.tolist(),quaternion=pose['quaternion']))
        self.assertEqual(len(calls),2)
        np.testing.assert_allclose(calls[1],np.asarray(pose['position'])+np.array([.002,0,0]))
        self.assertLess(np.max(np.abs(result-measured)),math.radians(15))
        np.testing.assert_allclose(self.sim.target,old_target)
        self.assertEqual(self.transport.writes,[])

    def test_vr_ik_never_accepts_persistent_branch_jump(self):
        from unittest.mock import patch
        self.motion.start(self.start_value,owner='vr')
        pose=self.sim.fk(self.motion.actual);old=self.sim.target.copy()
        with self.sim.lock,patch.object(self.sim,'_ik',return_value=(self.motion.actual+.3,{})):
            with self.assertRaisesRegex(ValueError,'仍跳变过大'):
                self.motion._vr_pose(pose)
        np.testing.assert_allclose(self.sim.target,old)
        self.assertEqual(self.transport.writes,[])

    def test_collision_path_and_large_ik_branch_changes_are_rejected(self):
        self.start()
        with self.assertRaises(ValueError):self.input(dict(type='pose',position=[10,10,10],quaternion=[0,0,0,1],gripper=40))
        self.motion.baseline={}
        q=np.array([.5693844361,1.867324172,.8398506467,-1.046914993,.8367071885,.5422002931])
        self.sim.command(dict(type='settings',obstacle=True))
        # Verify actual swept checks, rather than an enable/disable UI flag.
        with self.assertRaises(CommandError):self.motion._path(self.motion.actual,q,40,40)
        self.assertEqual(self.transport.writes,[])

    def test_api_same_origin_owner_and_simulation_exclusion(self):
        class Quiet(Handler):
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=self.temp.name))
        http.simulation=self.sim;http.hardware_motion=self.motion;http.hardware_operations=self.operations
        Thread(target=http.serve_forever,daemon=True).start()
        self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        def post(path,value,origin=True):
            conn=HTTPConnection('127.0.0.1',http.server_port)
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=f'http://127.0.0.1:{http.server_port}'
            conn.request('POST',path,json.dumps(value),headers);response=conn.getresponse();result=response.status,json.loads(response.read());conn.close();return result
        self.assertEqual(post('/api/hardware/mouse/start',self.start_value,False)[0],403)
        self.assertEqual(self.transport.writes,[])
        self.assertEqual(post('/api/hardware/mouse/start',self.start_value)[0],200)
        self.assertEqual(post('/api/sim/command',dict(type='reset'))[0],400)
        self.assertEqual(post('/api/vr-bridge/vr/enter',{})[0],409)
        self.assertEqual(post('/api/hardware/mouse/input',dict(token='old',sequence=1))[0],400)
        self.assertEqual(post('/api/hardware/mouse/stop',{})[0],200)
        self.assertEqual(post('/api/sim/command',dict(type='reset'))[0],200)


class MotionFrameTests(unittest.TestCase):
    def test_native_sdk_position_speed_and_mode_frames_offline(self):
        sdk=Path(os.environ.get('ROBODATA_S1_SDK', str(ROOT.parent/'14-DOF robotic arm/S1_SDK_V2')))/'src/S1_SDK/hardware'
        if sys.version_info[:2]!=(3,10) or not sdk.exists():self.skipTest('SDK oracle not installed')
        from S1_SDK.hardware import motor_interface
        lib=ctypes.CDLL(motor_interface.__file__)
        ctor=getattr(lib,'_ZN6damiaoC1Ejj');ctor.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        delete=getattr(lib,'_ZdlPv');delete.argtypes=[ctypes.c_void_p]
        for node in range(1,8):
            for mode in (False,True):
                obj=ctypes.create_string_buffer(64);ctor(obj,node,1)
                result=ctypes.create_string_buffer(24)
                if mode:
                    function=getattr(lib,'_ZN6damiao10switchmodeEi');function.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
                    function(result,obj,2);expected=position_mode(node)
                else:
                    function=getattr(lib,'_ZN6damiao15control_pos_velEff');function.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_float,ctypes.c_float]
                    function(result,obj,.7 if node!=7 else -.7,.05);expected=position_velocity(node,.7,.05)
                begin,end,_=struct.unpack('PPP',result.raw)
                try:
                    self.assertEqual(end-begin,12)
                    can_id,data=struct.unpack('=I8s',ctypes.string_at(begin,12))
                    self.assertEqual(struct.pack('=IB3x8s',can_id,8,data),expected)
                finally:delete(begin)

    def test_position_encoder_rejects_unsafe_values(self):
        for node,pos,vel in [(0,0,.05),(1,0,0),(1,99,.05),(1,0,10),(7,float('nan'),.05),(1,0,float('inf'))]:
            with self.assertRaises(ValueError):position_velocity(node,pos,vel)


if __name__=='__main__':unittest.main()
