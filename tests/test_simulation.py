import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from backend.simulation import Simulation, CommandError


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(start_worker=False)

    def tearDown(self):
        self.sim.close()

    def test_pose_roundtrip_and_nearby_target(self):
        pose = self.sim.state()['tcp']
        pose['position'][2] += .02
        result = self.sim.command({'type': 'pose', **{k: pose[k] for k in ('position', 'quaternion')}})
        self.assertLess(result['ik_residual']['position_mm'], .5)
        self.assertLess(result['ik_residual']['orientation_deg'], 1)
        np.testing.assert_allclose(result['tcp']['position'], pose['position'], atol=.0005)

    def test_orientation_target(self):
        pose = self.sim.state()['tcp']
        delta = Rotation.from_rotvec([.08, 0, 0])
        quaternion = (delta*Rotation.from_quat(pose['quaternion'])).as_quat()
        result = self.sim.command({'type': 'pose', 'position': pose['position'], 'quaternion': quaternion.tolist()})
        self.assertLess(result['ik_residual']['orientation_deg'], 1)

    def test_unreachable_preserves_accepted_state(self):
        before = self.sim.state()
        with self.assertRaises(CommandError) as error:
            self.sim.command({'type': 'pose', 'position': [5, 0, 0], 'quaternion': [0, 0, 0, 1]})
        self.assertEqual(error.exception.code, 'UNREACHABLE')
        self.assertEqual(before['joints'], self.sim.state()['joints'])
        self.assertEqual(before['target_joints'], self.sim.state()['target_joints'])

    def test_zero_start_reset_and_vr_pose(self):
        np.testing.assert_array_equal(self.sim.state()['joints'], [0]*6)
        self.assertFalse(self.sim.state()['vr_mode'])
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.sim.step(100)
        np.testing.assert_array_equal(self.sim.state()['joints'], [0]*6)
        self.assertEqual(self.sim.state()['contacts'], [])
        pose = self.sim.state()['tcp']
        for step in range(1, 6):
            target = list(pose['position']); target[2] += .002*step
            result = self.sim.command(dict(type='pose', position=target,
                quaternion=pose['quaternion'], expected_revision=self.sim.revision))
            self.assertFalse(result['contacts'])
            self.assertLess(result['ik_residual']['position_mm'], .5)
        result = self.sim.command({'type': 'reset'})
        np.testing.assert_array_equal(result['joints'], self.sim.spec['homeRadians'])
        self.assertFalse(result['contacts'])

    def test_vr_mode_entry_reset_and_exit(self):
        home=self.sim.spec['vrGrabRadians']
        self.sim.command({'type':'vr_enter'})
        saw_zero=False
        for _ in range(1500):
            self.sim.step()
            saw_zero |= np.max(np.abs(self.sim.state()['joints'])) < 1e-9
        self.assertTrue(saw_zero)
        np.testing.assert_allclose(self.sim.state()['joints'],home)
        self.assertTrue(self.sim.state()['vr_mode'])
        self.sim.command({'type':'joints','joints':[0,1.1,1.55,.5,0,0]})
        self.sim.command({'type':'reset'})
        self.assertTrue(self.sim.state()['vr_preparing'])
        with self.assertRaises(CommandError): self.sim.command({'type':'joints','joints':home})
        for _ in range(200): self.sim.step()
        np.testing.assert_allclose(self.sim.state()['joints'],home)
        self.sim.command({'type':'vr_exit'})
        self.assertFalse(self.sim.state()['vr_mode'])
        self.assertTrue(self.sim.state()['vr_preparing'])
        np.testing.assert_allclose(self.sim.state()['joints'],home)
        before=np.array(self.sim.state()['joints'])
        self.sim.step()
        after=np.array(self.sim.state()['joints'])
        self.assertGreater(np.max(np.abs(after)),0)
        self.assertLessEqual(np.max(np.abs(after-before)),.005+1e-12)
        for _ in range(500): self.sim.step()
        self.assertFalse(self.sim.state()['vr_preparing'])
        np.testing.assert_array_equal(self.sim.state()['joints'], [0]*6)
        self.sim.command({'type':'vr_enter'})
        self.sim.step();self.sim.command({'type':'pause'})
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.assertTrue(self.sim.state()['vr_mode'])

    def test_vr_rejects_remote_ik_branch(self):
        from unittest.mock import patch
        with patch.object(self.sim, '_ik', return_value=(np.array([1.,0,0,0,0,0]), {})):
            with self.assertRaises(CommandError) as e:
                self.sim.command(dict(type='pose', position=[0,0,0], quaternion=[0,0,0,1], expected_revision=0))
        self.assertEqual(e.exception.code, 'IK_BRANCH_JUMP')
        np.testing.assert_array_equal(self.sim.state()['joints'], self.sim.spec['homeRadians'])

    def test_vr_entry_and_reset_restore_gripper(self):
        home = self.sim.spec['vrGrabRadians']
        for initial, action in ((0., 'vr_enter'), (100., 'reset')):
            with self.subTest(initial=initial, action=action):
                self.sim.command({'type':'joints', 'joints':self.sim.state()['joints'], 'gripper':initial})
                self.sim.command({'type':action})
                self.assertAlmostEqual(self.sim.state()['gripper'], initial)
                previous = self.sim.state()
                for _ in range(1500):
                    self.sim.step()
                    state = self.sim.state()
                    self.assertLessEqual(abs(state['gripper']-previous['gripper']), .5+1e-9)
                    self.assertLessEqual(np.max(np.abs(np.array(state['joints'])-previous['joints'])), .005+1e-9)
                    self.assertFalse(state['contacts'])
                    previous = state
                    if not state['vr_preparing']: break
                self.assertFalse(state['vr_preparing'])
                np.testing.assert_allclose(state['joints'], home)
                self.assertAlmostEqual(state['gripper'], 40.)
                self.assertAlmostEqual(state['target_gripper'], 40.)

    def test_vr_reset_gripper_only_and_pause(self):
        home = self.sim.spec['vrGrabRadians']
        self.sim.command({'type':'joints', 'joints':home, 'gripper':0.})
        self.sim.vr_mode = True
        self.sim.command({'type':'reset'})
        self.sim.step()
        self.assertTrue(self.sim.state()['vr_preparing'])
        self.assertAlmostEqual(self.sim.state()['gripper'], .5)
        self.sim.command({'type':'pause'})
        paused = self.sim.state()
        self.sim.step(500)
        self.assertAlmostEqual(self.sim.state()['gripper'], paused['gripper'])
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.sim.command({'type':'reset'})
        for _ in range(100): self.sim.step()
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.assertAlmostEqual(self.sim.state()['gripper'], 40.)

    def test_vr_gripper_collision_keeps_accepted_state(self):
        from unittest.mock import patch
        home = self.sim.spec['vrGrabRadians']
        self.sim.command({'type':'joints', 'joints':home, 'gripper':0.})
        self.sim.vr_mode = True
        before = self.sim.state()
        collision = [{'pair':['6_Link','floor'], 'penetration_mm':1.}]
        with patch.object(self.sim, '_check_path', return_value=collision) as check:
            with self.assertRaises(CommandError): self.sim.command({'type':'reset'})
            self.assertEqual(check.call_args.args[2:], (0., 40.))
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.assertEqual(self.sim.state()['gripper'], before['gripper'])
        self.sim.command({'type':'reset'})
        with patch.object(self.sim, '_check_path', return_value=collision): self.sim.step()
        self.assertFalse(self.sim.state()['vr_preparing'])
        self.assertEqual(self.sim.state()['gripper'], before['gripper'])
        self.assertTrue(self.sim.state()['fault'])

    def test_collision_rejection_and_explicit_override(self):
        # Use a known obstacle collision, rather than the former zero-pose hull false positive.
        q = [.5693844361, 1.867324172, .8398506467, -1.046914993, .8367071885, .5422002931]
        self.sim.command({'type': 'settings', 'obstacle': True})
        before = self.sim.state()['joints']
        with self.assertRaises(CommandError) as error:
            self.sim.command({'type': 'joints', 'joints': q})
        self.assertEqual(error.exception.code, 'COLLISION')
        self.assertTrue(error.exception.contacts)
        self.assertEqual(self.sim.state()['joints'], before)
        self.sim.command({'type': 'settings', 'collision_protection': False})
        self.sim.command({'type': 'joints', 'joints': q})
        self.assertTrue(self.sim.state()['contacts'])

    def test_environment_obstacle_can_be_enabled(self):
        q = [.5693844361, 1.867324172, .8398506467, -1.046914993, .8367071885, .5422002931]
        self.sim.command({'type': 'settings', 'obstacle': True})
        self.sim._put(self.sim.scratch, q, 40)
        self.assertTrue(any('obstacle' in c['pair'] for c in self.sim._contacts(self.sim.scratch)))
        self.sim.command({'type': 'settings', 'obstacle': False})
        self.sim._put(self.sim.scratch, q, 40)
        self.assertFalse(any('obstacle' in c['pair'] for c in self.sim._contacts(self.sim.scratch)))

    def test_dynamics_holds_and_tracks_using_steps(self):
        self.sim.command({'type': 'settings', 'mode': 'dynamic'})
        self.sim.command({'type': 'resume'})
        before = self.sim.state()['joints']
        for _ in range(200):
            self.sim.step(5)
        result = self.sim.state()
        self.assertTrue(result['running'], result['fault'])
        self.assertGreater(result['simulation_time'], 1.9)
        np.testing.assert_allclose(result['joints'], before, atol=.01)
        q = np.array(before); q[0] += .15
        self.sim.command({'type': 'joints', 'joints': q.tolist()})
        # Command changes the controller target, never teleports actual qpos.
        np.testing.assert_allclose(self.sim.state()['joints'], before, atol=.01)
        for _ in range(300):
            self.sim.step(5)
        result = self.sim.state()
        np.testing.assert_allclose(result['joints'], q, atol=.02)
        self.assertTrue(result['running'], result['fault'])
        self.sim.command({'type': 'pause'})
        before = self.sim.state()
        self.sim.step(10)
        self.assertEqual(self.sim.state()['simulation_time'], before['simulation_time'])

    def test_validation_and_gripper_independence(self):
        before = self.sim.state()['joints']
        for grip in [0, 50, 100]:
            result = self.sim.command({'type': 'joints', 'joints': before, 'gripper': grip})
            np.testing.assert_allclose(result['joints'], before)
            self.assertAlmostEqual(result['gripper'], grip)
        for request in [
            {'type': 'joints', 'joints': [float('nan')]*6},
            {'type': 'joints', 'joints': [20]*6},
            {'type': 'pose', 'position': [0, 0, 0], 'quaternion': [0]*4},
            {'type': 'settings', 'collision_protection': 'false'},
            {'type': 'pose', 'position': [0, 0, 0], 'quaternion': [0, 0, 0, 1], 'position_only': 'false'},
        ]:
            with self.assertRaises(CommandError):
                self.sim.command(request)

    def test_external_settings_and_atomic_runtime_validation(self):
        sim = Simulation(start_worker=False, settings={'speed_rad_s': .35, 'ik_position_tolerance_mm': .2, 'obstacle': True})
        try:
            state = sim.state()
            self.assertEqual(state['speed_rad_s'], .35)
            self.assertEqual(state['ik_position_tolerance_mm'], .2)
            self.assertTrue(state['obstacle'])
            sim.command({'type': 'settings', 'speed_rad_s': .42, 'ik_orientation_tolerance_deg': .8})
            with self.assertRaises(CommandError):
                sim.command({'type': 'settings', 'speed_rad_s': .7, 'ik_orientation_tolerance_deg': -1, 'obstacle': False})
            state = sim.state()
            self.assertEqual(state['speed_rad_s'], .42)
            self.assertEqual(state['ik_orientation_tolerance_deg'], .8)
            self.assertTrue(state['obstacle'])
        finally:
            sim.close()


if __name__ == '__main__':
    unittest.main()
