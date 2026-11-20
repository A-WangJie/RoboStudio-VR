import sys
import math
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from pose_controls import PoseControls, robot_delta, angle, toward, IDENTITY

def quat(axis,degrees):
    q=[0.,0.,0.,math.cos(math.radians(degrees)/2)]
    q[axis]=math.sin(math.radians(degrees)/2)
    return q

class PoseTests(unittest.TestCase):
    def test_axis_handedness(self):
        for axis,expected in [(0,quat(1,20)),(1,quat(2,-20)),(2,quat(0,-20))]:
            self.assertLess(angle(robot_delta(quat(axis,20),IDENTITY),expected),1e-7)
    def test_clutch_no_jump_rate_and_gripper(self):
        c=PoseControls();h=dict(rotation=quat(1,25),trigger=.6)
        q,g=c.goals(h,1,IDENTITY,40,0,True,True)
        self.assertEqual(q,IDENTITY);self.assertEqual(g,40)
        h=dict(rotation=quat(1,45),trigger=1)
        q,g=c.goals(h,1,q,g,.1,True,True)
        self.assertLessEqual(angle(q,IDENTITY),math.radians(9)+1e-7)
        self.assertEqual(g,35)
        saved=list(q)
        q,g=c.goals(dict(rotation=quat(0,70),trigger=0),2,q,g,.2,True,True)
        self.assertLess(angle(q,saved),1e-7);self.assertEqual(g,35)
    def test_disabled_and_sign_equivalent(self):
        c=PoseControls();h=dict(rotation=IDENTITY,trigger=0)
        c.goals(h,1,IDENTITY,40,0,False,False)
        q,g=c.goals(dict(rotation=quat(0,90),trigger=1),1,IDENTITY,40,.1,False,False)
        self.assertEqual(g,40);self.assertEqual(q,IDENTITY)
        self.assertLess(angle(toward(IDENTITY,[0,0,0,-1],.01),IDENTITY),1e-7)
    def test_limit_and_jump(self):
        c=PoseControls();c.goals(dict(rotation=IDENTITY,trigger=0),1,IDENTITY,40,0,True,True)
        q=IDENTITY;g=40
        for i in range(1,41):q,g=c.goals(dict(rotation=quat(2,80),trigger=1),1,q,g,i*.1,True,True)
        self.assertAlmostEqual(angle(q,IDENTITY),math.radians(80))
        self.assertEqual(g,0)
        with self.assertRaises(ValueError): c.goals(dict(rotation=quat(2,-80),trigger=1),1,q,g,5,True,True)

if __name__=='__main__':unittest.main()
