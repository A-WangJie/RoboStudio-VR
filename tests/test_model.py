"""Validate the imported rig against the SDK's MuJoCo model, without hardware."""
import hashlib
import json
from pathlib import Path
import unittest

import mujoco
import numpy as np

ASSETS = Path(__file__).resolve().parents[1] / 'app/assets/s1_v1'


def quaternion_matrix(values):
    w, x, y, z = np.asarray(values) / np.linalg.norm(values)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def transforms(spec, values):
    result = {}

    def visit(body, parent):
        local = np.eye(4)
        local[:3, :3] = quaternion_matrix(body['quaternionWXYZ'])
        local[:3, 3] = body['position']
        if 'joint' in body:
            joint = body['joint']
            value = values[joint['name']]
            axis = np.asarray(joint['axis'], dtype=float)
            axis /= np.linalg.norm(axis)
            motion = np.eye(4)
            if joint['type'] == 'slide':
                motion[:3, 3] = axis * value
            else:
                x, y, z = axis
                skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
                motion[:3, :3] = np.eye(3) + np.sin(value)*skew + (1-np.cos(value))*(skew@skew)
                pivot = np.asarray(joint['position'])
                motion[:3, 3] = pivot - motion[:3, :3] @ pivot
            local = local @ motion
        world = parent @ local
        result[body['name']] = world
        for child in body['children']:
            visit(child, world)
    for body in spec['bodies']:
        visit(body, np.eye(4))
    return result


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ASSETS / 'model.json').read_text())
        cls.model = mujoco.MjModel.from_xml_path(str(ASSETS / 'source.xml'))

    def test_assets_match_import_manifest(self):
        self.assertEqual(hashlib.sha256((ASSETS/'source.xml').read_bytes()).hexdigest(), self.spec['sourceSha256'])
        for asset in self.spec['assets'].values():
            self.assertEqual(hashlib.sha256((ASSETS/asset['file']).read_bytes()).hexdigest(), asset['sha256'])
        self.assertEqual(len(self.spec['armJoints']), 6)
        self.assertEqual(len(self.spec['gripperJoints']), 2)

    def test_all_body_transforms_against_mujoco(self):
        rng = np.random.default_rng(42)
        data = mujoco.MjData(self.model)
        for _ in range(25):
            values = {}
            for i in range(self.model.njnt):
                name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, i)
                lower, upper = self.model.jnt_range[i]
                value = float(rng.uniform(lower, upper))
                if name == '8joint':
                    value = values['7joint']
                values[name] = value
                data.qpos[self.model.jnt_qposadr[i]] = value
            mujoco.mj_forward(self.model, data)
            for name, matrix in transforms(self.spec, values).items():
                body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
                np.testing.assert_allclose(matrix[:3, 3], data.xpos[body], atol=1e-9)
                np.testing.assert_allclose(matrix[:3, :3], data.xmat[body].reshape(3, 3), atol=1e-9)

    def test_reference_poses(self):
        poses = json.loads((Path(__file__).parent/'expected_poses.json').read_text())
        data = mujoco.MjData(self.model)
        body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, self.spec['tip']['body'])
        for pose in poses:
            data.qpos[:6] = pose['jointsRadians']
            mujoco.mj_forward(self.model, data)
            point = data.xpos[body] + data.xmat[body].reshape(3, 3) @ self.spec['tip']['position']
            np.testing.assert_allclose(point*1000, pose['tipMillimeters'], atol=1e-6)


if __name__ == '__main__':
    unittest.main()
