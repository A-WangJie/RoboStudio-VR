import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from server import State
from simulation_link import SimulationLink
from test_bridge import packet

class LinkTests(unittest.TestCase):
    def setUp(self):
        self.state=State();self.state.connected=True
        self.state.packet=packet();self.state.packet['source']='quest'
        self.state.received=time.monotonic()
        self.calls=[]
        def request(path,p=None):
            if p:
                self.calls.append(p)
                return dict(revision=4)
            return dict(vr_mode=True,vr_preparing=False,engine='MuJoCo test',mode='kinematic',collision_protection=True,revision=3,
                        tcp=dict(position=[.3,0,.2],quaternion=[0,0,0,1]))
        self.link=SimulationLink(self.state,request)
    def active(self):
        self.state.mapping.require_release=False
        self.state.mapping.anchor_hand=[0,0,0]
        self.state.mapping.target=[0,0,.01]
    def test_disabled_then_pose(self):
        self.active();self.link.tick();self.assertFalse(self.calls)
        self.link.enable();self.active();self.link.last_tick=time.monotonic()-.05;self.link.tick()
        p=self.calls[-1];self.assertFalse(p['position_only']);self.assertEqual(p['expected_revision'],3)
        self.assertAlmostEqual(p['position'][2],.21)
    def test_stale_and_fault_disarm(self):
        self.link.enable();self.active();self.state.received-=1;self.link.tick()
        self.assertFalse(self.link.enabled);self.assertFalse(self.calls)
        self.state.received=time.monotonic();self.link.enable();self.active()
        def fail(*args):raise ValueError('COLLISION')
        self.link.request=fail;self.link.tick();self.assertFalse(self.link.enabled)
    def test_close_page_and_release_hold(self):
        self.link.enable();self.active();self.link.viewer_seen-=3;self.link.tick()
        self.assertFalse(self.link.enabled);self.assertFalse(self.calls)
        self.link.enable();self.link.tick();self.assertFalse(self.calls)
    def test_stationary_rotation_and_gripper(self):
        self.link.enable(True,True);self.active();self.state.mapping.target=[0,0,0]
        self.link.tick()
        self.state.packet['right']['trigger']=.8
        self.link.pose_controls.last_time-=.1
        self.link.tick()
        self.assertEqual(len(self.calls),1)
        self.assertLess(self.calls[0]['gripper'],40)
        self.assertEqual(self.calls[0]['position'],[.3,0,.2])
    def test_bind_current_workbench(self):
        self.link.bind_port(43210)
        self.assertEqual(self.link.port,43210)
        self.link.enabled=True
        with self.assertRaises(ValueError):self.link.bind_port(8765)
        self.link.enabled=False;self.link.mode_state={'vr_mode':True}
        with self.assertRaises(ValueError):self.link.bind_port(8765)
        with self.assertRaises(ValueError):self.link.bind_port(80)

    def test_gripped_enable_rejected(self):
        self.state.packet['right']['grip']=1
        with self.assertRaises(ValueError):self.link.enable()

if __name__=='__main__':unittest.main()
