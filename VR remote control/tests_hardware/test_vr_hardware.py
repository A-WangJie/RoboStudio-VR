"""No devices: Quest packets -> shared motion controller -> memory-only motors."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'VR remote control'));sys.path.insert(0,str(ROOT/'tests'))
from backend.hardware import HardwareDiagnostics
from backend.hardware_operations import HardwareOperations
from backend.hardware_motion import HardwareMotion
from backend.simulation import Simulation
from hardware_control import VRHardwareControl
from test_hardware_mouse import MotionTransport
from bridge.simulation_link import SimulationLink


def packet():
    h=dict(connected=True,tracked=True,primary=False,secondary=False,position=[0.,1.,0.],rotation=[0.,0.,0.,1.],stick=[0.,0.],trigger=.5,grip=0.)
    return dict(version=1,source='quest',seq=1,timeMs=1000.,focused=True,left=deepcopy(h),right=deepcopy(h))


class VRHardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=[10.];self.p=packet();self.s=dict(status='live',packet=self.p,ageMs=0,error='',network=dict(extraDelayMs=0))
        self.transport=MotionTransport('can0')
        self.sim=Simulation(start_worker=False);self.addCleanup(self.sim.close)
        self.config=dict(layout='single',timeoutMs=500,arms=[dict(id=c,device=f'can{i}',bitrate=1000000,endEffector='gripper') for i,c in enumerate('AB')])
        self.file=Path(self.temp.name)/'arms.json';self.file.write_text(json.dumps(dict(connection=dict(layout='single',timeoutMs=500),arms=self.config['arms'])))
        diagnostics=HardwareDiagnostics(lambda:[dict(device='can0',up=True,busState='ERROR-ACTIVE',bitrate=1000000)],lock_path=Path(self.temp.name)/'lock')
        operations=HardwareOperations(diagnostics,lambda _:self.transport,Path(self.temp.name)/'audit.jsonl')
        self.motion=HardwareMotion(operations,self.sim,self.file,start_worker=False,clock=lambda:self.clock[0])
        self.vr=VRHardwareControl(self.motion,lambda:deepcopy(self.s),start_worker=False,clock=lambda:self.clock[0])
        self.addCleanup(self.vr.stop)
        self.options=dict(config=self.config,armId='A',confirmed=True,speedDegS=3,gripper=None,orientation=True,gripperEnabled=False,positionGain=1)

    def start(self):return self.vr.start(self.options)
    def tick(self,view=True,new=True):
        self.clock[0]+=.05
        if new:self.p['seq']+=1;self.p['timeMs']+=50
        if view:self.vr.touch(dict(viewerToken=self.vr.viewer_token))
        self.motion.tick();self.vr.tick()
    def ready(self):
        self.start()
        for _ in range(230):
            self.tick()
            if not self.vr.preparing:break
        self.assertTrue(self.vr.active,self.vr.message);self.assertEqual(self.vr.phase,'ready')

    def test_no_automatic_hardware_from_snapshots_or_rd_shortcuts(self):
        for _ in range(5):self.vr.state();self.vr.tick()
        with self.assertRaises(ValueError):self.vr.command('follow')
        with self.assertRaises(ValueError):self.vr.command('grasp')
        self.assertEqual(self.transport.writes,[])

    def test_enter_requires_real_fresh_released_quest_enabled_motors_and_confirmation(self):
        mutations=[lambda:self.s.update(ageMs=251),lambda:self.p.update(source='simulated'),lambda:self.p.update(focused=False),
            lambda:self.p['right'].update(grip=1),lambda:self.p['right'].update(tracked=False),lambda:self.p.update(uiInteracting=True),
            lambda:self.s['network'].update(extraDelayMs=151),lambda:self.options.update(confirmed=False),lambda:setattr(self.transport,'enabled',False)]
        for mutate in mutations:
            original=deepcopy((self.s,self.options));mutate()
            with self.assertRaises((ValueError,OSError)):self.start()
            self.s,self.options=original;self.p=self.s['packet'];self.transport.enabled=True
        self.assertEqual(self.transport.writes,[])

    def test_enter_prepares_grasp_slowly_then_requires_explicit_follow(self):
        result=self.start();self.assertEqual(self.motion.owner,'vr');self.assertTrue(result['preparing'])
        self.assertEqual(self.transport.writes,[])
        with self.assertRaisesRegex(ValueError,'等待'):self.vr.command('follow')
        self.tick();self.assertTrue(self.transport.writes)
        for _ in range(230):
            self.tick()
            if not self.vr.preparing:break
        self.assertTrue(self.vr.active,self.vr.message);self.assertFalse(self.vr.enabled)
        np.testing.assert_allclose(self.transport.q[:6],self.sim.spec['vrGrabRadians'],atol=math.radians(.6))
        self.assertTrue(self.transport.enabled)

    def test_clutch_translation_release_and_regrip_have_no_queued_destination(self):
        self.ready();self.vr.command('follow')
        self.p['right']['grip']=1.;self.tick();count=self.vr.sent
        self.assertEqual(count,0,'First grasp only records relative origin')
        for _ in range(8):self.p['right']['position'][2]+=.001;self.tick()
        self.assertTrue(self.vr.active,self.vr.message);self.assertGreater(self.vr.sent,0)
        self.p['right']['grip']=0.;self.tick();q=np.array(self.transport.q[:6]);sent=self.vr.sent
        for _ in range(5):self.p['right']['position'][2]+=.02;self.tick()
        np.testing.assert_allclose(self.transport.q[:6],q);self.assertEqual(self.vr.sent,sent)
        self.p['right']['grip']=1.;self.tick();self.assertEqual(self.vr.sent,sent)

    def test_explicit_position_mode_reaches_position_only_solver(self):
        self.options['positionOnly']=True
        self.ready();self.vr.command('follow');self.p['right']['grip']=1.;self.tick()
        original=self.motion._vr_pose;requests=[]
        def record(payload):
            requests.append(deepcopy(payload));return original(payload)
        self.motion._vr_pose=record
        self.p['right']['position'][2]+=.002;self.tick()
        self.assertTrue(self.vr.active,self.vr.message)
        self.assertTrue(requests[-1]['position_only'])

    def test_orientation_and_gripper_request_integrate_without_encoder_reanchoring(self):
        from scipy.spatial.transform import Rotation
        from bridge.pose_controls import angle
        self.options.update(gripperEnabled=True,gripper=dict(closedDeg=0,openDeg=90))
        self.transport.q[:6]=self.sim.spec['vrGrabRadians'];self.transport.q[6]=math.radians(36)
        self.ready();self.vr.command('follow');self.p['right']['grip']=1.;self.tick()
        original_rotation=list(self.vr.rotation);original_opening=self.vr.opening
        commands=[]
        # Isolate the request generator from servos: encoders deliberately stay
        # at the anchor while requested rotation/trigger move for four packets.
        send=self.vr._send
        def record(command=None):
            if command and command['type']=='pose':commands.append(deepcopy(command));return self.motion.state()
            return send(command)
        self.vr._send=record
        for i in range(4):
            self.p['right']['rotation']=Rotation.from_euler('y',(i+1)*4,degrees=True).as_quat().tolist()
            self.p['right']['trigger']=.9
            self.tick()
        self.assertTrue(self.vr.active,self.vr.message)
        self.assertGreater(angle(commands[-1]['quaternion'],original_rotation),math.radians(12))
        self.assertAlmostEqual(commands[-1]['gripper'],original_opening-10,places=6)
        self.assertAlmostEqual(self.vr.state()['tracking']['speedDegS'],3)

    def test_fast_translation_has_bounded_lead_and_release_clears_backlog(self):
        self.ready();self.vr.command('follow');self.p['right']['grip']=1.;self.tick()
        for _ in range(12):
            self.p['right']['position'][2]+=.002;self.tick()
            self.assertTrue(self.vr.active,self.vr.message)
            self.assertLessEqual(self.vr.state()['tracking']['targetLeadMm'],20.)
        self.p['right']['grip']=0.;self.tick();held=np.array(self.transport.q[:6])
        self.assertIsNone(self.vr.state()['tracking'])
        for _ in range(10):self.tick()
        np.testing.assert_allclose(self.transport.q[:6],held)

    def test_coordinated_joint_step_preserves_ratios_speed_and_acceleration(self):
        target=np.array([.2,.1,-.05,.04,0.,0.]);q=np.zeros(6);v=np.zeros(6)
        for _ in range(10):
            next_q,next_v=HardwareMotion.coordinated_ramp(q,v,target,math.radians(10),.05)
            np.testing.assert_allclose(next_q[:4]/target[:4],np.repeat(next_q[0]/target[0],4),atol=1e-10)
            self.assertLessEqual(float(np.max(np.abs(next_v))),math.radians(10)+1e-10)
            self.assertLessEqual(float(np.max(np.abs(next_v-v))),HardwareMotion.ACCELERATION*.05+1e-10)
            q,v=next_q,next_v

    def test_A_reanchors_B_resets_and_explicit_exit_returns_zero(self):
        self.ready();self.vr.command('follow');self.p['right']['grip']=1.;self.tick()
        with self.assertRaisesRegex(ValueError,'松开'):self.vr.command('follow')
        self.p['right']['grip']=0.;self.tick();self.vr.command('follow')
        self.vr.command('grasp');self.assertTrue(self.vr.preparing);self.assertFalse(self.vr.enabled)
        before=np.array(self.transport.q[:6]);self.vr.command('exit')
        self.assertTrue(self.vr.active);self.assertEqual(self.vr.phase,'returning-zero')
        self.assertFalse(self.vr.enabled)
        for _ in range(650):
            self.tick()
            if not self.vr.active:break
        self.assertFalse(self.vr.active,self.vr.message)
        np.testing.assert_allclose(self.transport.q[:6],np.zeros(6),atol=math.radians(.5))
        self.assertTrue(self.transport.enabled);self.assertTrue(self.vr.selected)
        with self.assertRaisesRegex(ValueError,'RS'):self.vr.command('follow')

    def test_return_zero_stop_and_feedback_loss_never_finish_old_target(self):
        self.ready();self.vr.command('zero');self.tick()
        self.vr.command('stop');held=list(self.transport.q)
        self.assertFalse(self.vr.active)
        self.vr.tick();np.testing.assert_allclose(self.transport.q,held)
        self.ready();self.vr.command('exit')
        self.transport.missing=True;self.motion.tick();self.vr.tick()
        self.assertFalse(self.vr.active);self.assertFalse(self.motion.active)

    def test_pause_cancels_zero_and_restores_ui_interlock(self):
        self.ready();self.vr.command('zero');self.vr.command('pause')
        self.assertFalse(self.vr.returning_zero);self.assertFalse(self.vr.preparing)
        self.vr.command('follow');self.p['uiInteracting']=True;self.vr.tick()
        self.assertTrue(self.vr.ui_paused);self.assertFalse(self.vr.enabled)

    def test_zero_button_hover_does_not_cancel_explicit_return(self):
        self.ready();self.p['uiInteracting']=True
        self.vr.command('zero');self.tick()
        self.assertEqual(self.vr.phase,'returning-zero');self.assertFalse(self.vr.ui_paused)
        self.p['right']['tracked']=False;self.vr.tick()
        self.assertFalse(self.vr.active)

    def test_tracking_stream_focus_delay_restart_all_stop(self):
        for failure in ('tracking','stale','focus','backlog','restart'):
            with self.subTest(failure=failure):
                self.s=dict(status='live',packet=packet(),ageMs=0,error='',network=dict(extraDelayMs=0));self.p=self.s['packet']
                self.start();self.tick();count=len(self.transport.writes)
                if failure=='tracking':self.p['right']['tracked']=False
                if failure=='stale':self.s['ageMs']=300
                if failure=='focus':self.p['focused']=False
                if failure=='backlog':self.s['network']['extraDelayMs']=200
                if failure=='restart':self.p['seq']=0;self.p['timeMs']=0
                self.vr.tick();self.assertFalse(self.vr.active,self.vr.message)
                self.assertFalse(self.motion.active);self.assertLessEqual(len(self.transport.writes),count+1)

    def test_rd_hover_pauses_follow_keeps_session_and_requires_explicit_reanchor(self):
        self.ready();self.vr.command('follow');self.p['right']['grip']=1;self.tick()
        self.p['right']['position'][2]+=.001;self.tick()
        token=self.vr.viewer_token;key=self.motion.token
        self.p['uiInteracting']=True;self.vr.tick()
        self.assertTrue(self.vr.active);self.assertTrue(self.motion.active)
        self.assertEqual(self.vr.phase,'ui-paused');self.assertTrue(self.vr.state()['uiPaused'])
        self.assertFalse(self.vr.enabled)
        held=list(self.transport.q);sent=self.vr.sent
        for _ in range(40):
            self.p['right']['position'][2]+=.01;self.p['right']['trigger']=1;self.tick()
        np.testing.assert_allclose(self.transport.q,held,atol=1e-12)
        self.assertEqual(self.vr.sent,sent)
        self.assertEqual(self.vr.viewer_token,token);self.assertEqual(self.motion.token,key)
        with self.assertRaisesRegex(ValueError,'移开射线'):self.vr.command('follow')
        with self.assertRaisesRegex(ValueError,'移开射线'):self.vr.command('grasp')
        self.p['uiInteracting']=False
        for _ in range(3):self.tick()
        self.assertTrue(self.vr.active);self.assertFalse(self.vr.enabled);self.assertFalse(self.vr.state()['uiPaused'])
        np.testing.assert_allclose(self.transport.q,held,atol=1e-12)
        with self.assertRaisesRegex(ValueError,'松开'):self.vr.command('follow')
        self.p['right']['grip']=0;self.tick();self.vr.command('follow')
        self.p['right']['grip']=1;self.tick()
        self.assertEqual(self.vr.sent,sent,'Fresh clutch must not chase the UI-time hand movement')
        self.p['right']['position'][2]+=.001;self.tick()
        self.assertGreater(self.vr.sent,sent)

    def test_rd_hover_cancels_preparation_without_exiting_or_auto_resuming(self):
        self.start();self.tick();token=self.vr.viewer_token
        self.p['uiInteracting']=True;self.vr.tick()
        held=list(self.transport.q)
        self.assertTrue(self.vr.active);self.assertFalse(self.vr.preparing)
        np.testing.assert_allclose(self.motion.target,held[:6],atol=1e-12)
        for _ in range(5):self.tick()
        self.p['uiInteracting']=False
        for _ in range(5):self.tick()
        np.testing.assert_allclose(self.transport.q,held,atol=1e-12)
        self.assertIn('按 B',self.vr.message);self.assertEqual(self.vr.viewer_token,token)
        self.vr.command('grasp');self.assertTrue(self.vr.preparing)
        self.assertEqual(self.vr.viewer_token,token)
        self.tick();self.assertTrue(self.vr.active)

    def test_ui_paused_still_enforces_tracking_and_page_lease(self):
        for failure in ('tracking','page','stale','can'):
            with self.subTest(failure=failure):
                self.s=dict(status='live',packet=packet(),ageMs=0,error='',network=dict(extraDelayMs=0));self.p=self.s['packet']
                self.transport.missing=False
                self.start();self.p['uiInteracting']=True;self.vr.tick()
                self.assertTrue(self.vr.active)
                if failure=='tracking':self.p['right']['tracked']=False
                if failure=='page':self.clock[0]+=1.6
                if failure=='stale':self.s['ageMs']=300
                if failure=='can':self.transport.missing=True;self.motion.tick()
                self.vr.tick()
                self.assertFalse(self.vr.active);self.assertFalse(self.motion.active)

    def test_page_token_not_get_snapshot_renews_and_loss_stops(self):
        self.start();self.tick()
        with self.assertRaises(ValueError):self.vr.touch(dict(viewerToken='wrong'))
        self.clock[0]+=1.6;self.vr.state();self.vr.tick()
        self.assertFalse(self.vr.active);self.assertIn('页面离线',self.vr.message)

    def test_mouse_vr_exclusion_and_gripper_calibration(self):
        self.start()
        with self.assertRaises(RuntimeError):self.motion.start(self.options)
        self.vr.stop();self.options['gripperEnabled']=True
        with self.assertRaisesRegex(ValueError,'夹爪'):self.start()
        self.options['gripper']=dict(closedDeg=0,openDeg=90);self.start();self.tick()
        self.assertIn(7,self.transport.writes[-1][0])
        self.assertLess(abs(self.transport.writes[-1][0][7]-1.5),math.radians(3)*.051)

    def test_reset_restores_calibrated_gripper_to_40_percent_not_40_degrees(self):
        self.options['gripper']=dict(closedDeg=0,openDeg=90)
        self.transport.q[:6]=self.sim.spec['vrGrabRadians']
        self.transport.q[6]=math.radians(36)
        self.ready();self.vr.command('follow')
        self.assertTrue(self.vr.enabled)
        self.transport.q[6]=math.radians(40)
        self.tick();self.vr.command('grasp')
        self.assertFalse(self.vr.enabled)
        for _ in range(80):
            self.tick()
            if not self.vr.preparing:break
        self.assertEqual(self.vr.phase,'ready',self.vr.message)
        self.assertAlmostEqual(self.transport.q[6],math.radians(36),delta=math.radians(1))
        self.assertTrue(all(7 in positions for positions,_,_ in self.transport.writes))

    def test_holding_uses_the_latest_measured_tcp_for_the_next_anchor(self):
        self.ready()
        self.transport.q[0]+=.002
        self.vr.command('follow')
        np.testing.assert_allclose(self.vr.base['position'],self.sim.fk(self.transport.q[:6])['position'],atol=1e-10)
        self.p['right']['grip']=1;self.tick()
        self.assertEqual(self.vr.sent,0)

    def test_selected_hardware_never_falls_back_on_service_loss(self):
        link=SimulationLink(None,lambda *_:dict(selected=True,active=False))
        link.hardware_status()
        def unavailable(*_):raise OSError('offline')
        link.request=unavailable
        with self.assertRaisesRegex(ValueError,'断开'):link.enable()
        link.bind_port(43210)
        self.assertEqual(link.hardware_state,{})

    def test_bridge_shortcuts_route_to_selected_real_controller_never_sim_commands(self):
        class Telemetry:pass
        calls=[]
        def request(path,body=None):
            calls.append((path,body))
            if path.endswith('/state'):return self.vr.state()
            if path.endswith('/command'):return self.vr.command(body['action'])
            raise AssertionError('Simulation endpoint must not receive a real command')
        link=SimulationLink(Telemetry(),request)
        self.ready()
        result=link.enable(True,False,1)
        self.assertEqual(result['execution'],'hardware');self.assertTrue(self.vr.enabled)
        link.mode_command('reset');self.assertTrue(self.vr.preparing)
        link.disable();self.assertFalse(self.vr.active)
        with self.assertRaises(ValueError):link.enable()
        self.assertFalse(any(path=='/api/sim/command' for path,_ in calls))


if __name__=='__main__':unittest.main()
