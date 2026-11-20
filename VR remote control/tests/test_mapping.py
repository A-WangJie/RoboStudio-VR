import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from mapping import Mapping

def packet(pos=(0,0,0),grip=0):
    return dict(source='quest',focused=True,right=dict(tracked=True,position=list(pos),grip=grip))

class MappingTests(unittest.TestCase):
    def test_directions_release_regrip(self):
        m=Mapping();m.update(packet(grip=1),True,0)
        self.assertTrue(m.require_release)
        m.update(packet(),True,0)
        m.update(packet(grip=1),True,.1)
        for i in range(1,41):m.update(packet((.1,.1,.1),1),True,.1+i*.05)
        for a,b in zip(m.target,[.1,-.1,.1]):self.assertAlmostEqual(a,b)
        saved=list(m.target);m.update(packet((.2,.2,.2)),True,2)
        self.assertEqual(m.target,saved)
        m.update(packet((.3,.3,.3),1),True,2.1)
        self.assertEqual(m.target,saved)
    def test_position_gain_and_repeated_clutch(self):
        m=Mapping(position_gain=2)
        now=0.
        for cycle in range(3):
            m.update(packet(),True,now)
            m.update(packet(grip=1),True,now+.01)
            for i in range(1,61):m.update(packet((0,-.1,0),1),True,now+.01+i*.05)
            now+=4
            m.update(packet((0,-.1,0)),True,now)
        self.assertAlmostEqual(m.target[2],-.6)
        self.assertEqual(m.target[:2],[0,0])
        for gain in (0,4,float('nan'),True):
            with self.assertRaises(ValueError):Mapping(position_gain=gain)

    def test_diagonal_is_not_distorted(self):
        m=Mapping(position_gain=.5)
        m.update(packet(),True,0);m.update(packet(grip=1),True,.01)
        for i in range(1,51):m.update(packet((.2,-.3,.4),1),True,.01+i*.02)
        for a,b in zip(m.target,[.2,-.1,-.15]):self.assertAlmostEqual(a,b)

    def test_wifi_batch_uses_sample_intervals(self):
        regular, burst = Mapping(), Mapping()
        for m in (regular, burst):
            p=packet();p['timeMs']=1000;m.update(p,True,0.)
            p=packet(grip=1);p['timeMs']=1030;m.update(p,True,.03)
        for i in range(1,6):
            p=packet((0,0,i*.01),1);p['timeMs']=1030+i*30
            regular.update(p,True,.03+i*.03)
            burst.update(p,True,.18+i*.0001)
        self.assertAlmostEqual(burst.target[0],regular.target[0])
        self.assertAlmostEqual(burst.target[0],.05)

    def test_loss_requires_release(self):
        m=Mapping();m.update(packet(),True,0);m.update(packet(grip=1),True,.1)
        m.update(None,False,.2);m.update(packet((.1,0,0),1),True,.3)
        self.assertEqual(m.target,[0,0,0]);self.assertTrue(m.require_release)
        p=packet();p['source']='simulated';m.update(p,True,.4)
        self.assertTrue(m.require_release)
    def test_speed_bound_and_jump(self):
        m=Mapping();m.update(packet(),True,0);m.update(packet(grip=1),True,.1)
        m.update(packet((0,0,.6),1),True,.15)
        self.assertLessEqual(m.target[0],.02000001)
        saved=list(m.target);m.update(packet((0,0,1),1),True,.2)
        self.assertEqual(m.target,saved);self.assertTrue(m.require_release)

if __name__=='__main__':unittest.main()
