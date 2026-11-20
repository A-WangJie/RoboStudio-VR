"""S1 simulation authority: MuJoCo FK, bounded IK, contacts and torque control."""
import json
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET
from .configuration import validate_simulation

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/assets/s1_v1'


class CommandError(ValueError):
    def __init__(self, code, message, contacts=None, residual=None):
        super().__init__(message)
        self.code, self.contacts, self.residual = code, contacts or [], residual


def vector(value, size, name):
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as error:
        raise CommandError('INVALID_INPUT', f'{name} 必须是有限数值数组') from error
    if result.shape != (size,) or not np.all(np.isfinite(result)):
        raise CommandError('INVALID_INPUT', f'{name} 必须包含 {size} 个有限数值')
    return result


class Simulation:
    DEFAULT_GRIPPER = 40.

    def __init__(self, start_worker=True, settings=None):
        settings = validate_simulation(settings or {})
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.spec = json.loads((ASSETS / 'model.json').read_text())
        xml = ET.parse(ASSETS / 'source.xml').getroot()
        xml.find('compiler').set('meshdir', str(ASSETS / 'meshes'))
        ET.SubElement(xml, 'option', timestep='0.002', gravity='0 0 -9.81', integrator='implicitfast')
        world = xml.find('worldbody')
        ET.SubElement(world, 'geom', name='floor', type='plane', size='2 2 0.05', pos='0 0 -0.054', rgba='0.2 0.25 0.3 1')
        ET.SubElement(world, 'geom', name='obstacle', type='box', size='0.05 0.05 0.10',
                      pos='0.30 0.16 0.20', contype='1', conaffinity='1')
        for body in xml.findall('.//body'):
            for geom in body.findall('geom'):
                geom.set('name', body.get('name'))
            if body.get('name') == self.spec['tip']['body']:
                ET.SubElement(body, 'site', name='tcp', pos=' '.join(map(str, self.spec['tip']['position'])), size='0.005')
        # Preserve the visual mesh; collision uses convex pieces so concavities
        # are not filled by a single whole-link convex hull.
        for name in ('2_Link', '5_Link'):
            parts = json.loads((ASSETS / 'collision' / (name + '.json')).read_text())
            body = xml.find(".//body[@name='" + name + "']")
            body.find('geom').set('contype', '0')
            body.find('geom').set('conaffinity', '0')
            for i, part in enumerate(parts):
                mesh_name = name + '_collision_' + str(i)
                ET.SubElement(xml.find('asset'), 'mesh', name=mesh_name,
                    vertex=' '.join(str(v) for row in part['vertices'] for v in row),
                    face=' '.join(str(v) for row in part['faces'] for v in row))
                ET.SubElement(body, 'geom', name=mesh_name, type='mesh', mesh=mesh_name,
                              group='3', rgba='0 0 0 0', mass='0')
        self.model = mujoco.MjModel.from_xml_string(ET.tostring(xml, encoding='unicode'))
        self.data, self.scratch = mujoco.MjData(self.model), mujoco.MjData(self.model)
        self.site = self.model.site('tcp').id
        self.arm_ids = [self.model.joint(name).id for name in self.spec['armJoints']]
        self.finger_ids = [self.model.joint(name).id for name in self.spec['gripperJoints']]
        self.qadr = self.model.jnt_qposadr[self.arm_ids]
        self.dadr = self.model.jnt_dofadr[self.arm_ids]
        self.fadr = self.model.jnt_qposadr[self.finger_ids]
        self.limits = self.model.jnt_range[self.arm_ids].copy()
        self.obstacle_id = self.model.geom('obstacle').id
        self.model.geom_contype[self.obstacle_id] = int(settings['obstacle'])
        self.model.geom_conaffinity[self.obstacle_id] = int(settings['obstacle'])
        self.target = np.array(self.spec['homeRadians'])
        self.servo = self.target.copy()
        self.gripper = self.DEFAULT_GRIPPER
        self.data.qpos[self.qadr] = self.target
        self.data.qpos[self.fadr] = self.gripper / 100 * .05
        self.mode = 'kinematic'
        self.running = False
        self.protection = settings['collision_protection']
        self.obstacle = settings['obstacle']
        self.speed = settings['speed_rad_s']
        self.ik_position_tolerance_mm = settings['ik_position_tolerance_mm']
        self.ik_orientation_tolerance_deg = settings['ik_orientation_tolerance_deg']
        self.fault = ''
        self.blocked = []
        self.command_count = 0
        self.last_command = time.monotonic()
        self.vr_mode = False
        self.vr_waypoints = []
        self.vr_gripper_target = self.gripper
        self.revision = 0
        self.sequence = 0
        mujoco.mj_forward(self.model, self.data)
        if start_worker:
            self.worker = threading.Thread(target=self._run, daemon=True, name='s1-mujoco')
            self.worker.start()

    def close(self):
        self.closed.set()
        if hasattr(self, 'worker'):
            self.worker.join(timeout=2)

    def _put(self, data, q, grip):
        data.qpos[self.qadr] = q
        data.qpos[self.fadr] = grip / 100 * .05
        data.qvel[:] = 0
        mujoco.mj_forward(self.model, data)

    def _contacts(self, data):
        pairs = {}
        for contact in data.contact:
            if contact.dist >= -1e-5:
                continue
            names = sorted([self.model.geom(contact.geom1).name.split('_collision_')[0], self.model.geom(contact.geom2).name.split('_collision_')[0]])
            key = tuple(names)
            pairs[key] = {'pair': names, 'penetration_mm': round(max(-contact.dist*1000,
                                      pairs.get(key, {}).get('penetration_mm', 0)), 3)}
        return list(pairs.values())

    def _check_path(self, start, end, grip_start, grip_end):
        # Discrete swept checks at <=1 degree and <=1 mm per finger.
        steps = max(1, int(np.ceil(np.max(np.abs(end-start)) / np.deg2rad(1))),
                    int(np.ceil(abs(grip_end-grip_start) * .5)))
        for fraction in np.linspace(0, 1, steps+1):
            self._put(self.scratch, start+(end-start)*fraction,
                      grip_start+(grip_end-grip_start)*fraction)
            contacts = self._contacts(self.scratch)
            if contacts:
                return contacts
        return []

    def fk(self, q, grip=40):
        with self.lock:
            q = vector(q, 6, 'joints')
            self._put(self.scratch, q, grip)
            return self._pose(self.scratch)

    def _pose(self, data):
        rotation = Rotation.from_matrix(data.site_xmat[self.site].reshape(3, 3))
        return {'position': data.site_xpos[self.site].tolist(),
                'quaternion': rotation.as_quat().tolist(),
                'rpy_deg': rotation.as_euler('xyz', degrees=True).tolist()}

    def _ik(self, position, quaternion, position_only):
        position = vector(position, 3, 'position（米）')
        quaternion = vector(quaternion, 4, 'quaternion（xyzw）')
        norm = np.linalg.norm(quaternion)
        if norm < 1e-8:
            raise CommandError('INVALID_INPUT', '目标四元数不能为零')
        target_rotation = Rotation.from_quat(quaternion/norm)
        if np.linalg.norm(position) > 1.2:
            raise CommandError('UNREACHABLE', '目标超出模型工作范围，保持上一姿态')
        seed = self.target.copy()

        def residual(q):
            self.scratch.qpos[self.qadr] = q
            mujoco.mj_kinematics(self.model, self.scratch)
            error = self.scratch.site_xpos[self.site] - position
            if position_only:
                # Small regularizer chooses the nearby solution of the redundant task.
                return np.r_[error, (q-seed)*1e-4]
            current = Rotation.from_matrix(self.scratch.site_xmat[self.site].reshape(3, 3))
            return np.r_[error, (current*target_rotation.inv()).as_rotvec() * .15]

        result = least_squares(residual, np.clip(seed, self.limits[:, 0]+1e-8, self.limits[:, 1]-1e-8),
                               bounds=(self.limits[:, 0], self.limits[:, 1]), max_nfev=100,
                               ftol=1e-9, xtol=1e-9, gtol=1e-9)
        residual(result.x)
        actual = self._pose(self.scratch)
        pos_error = np.linalg.norm(np.asarray(actual['position'])-position)
        rot_error = np.linalg.norm((Rotation.from_quat(actual['quaternion'])*target_rotation.inv()).as_rotvec())
        errors = {'position_mm': float(pos_error*1000), 'orientation_deg': float(np.rad2deg(rot_error))}
        if pos_error*1000 > self.ik_position_tolerance_mm or (not position_only and np.rad2deg(rot_error) > self.ik_orientation_tolerance_deg):
            raise CommandError('IK_FAILED', '未找到满足限位的邻近逆解，保持上一姿态', residual=errors)
        return result.x, errors

    def _snapshot(self):
        self.sequence += 1
        return {'vr_mode': self.vr_mode, 'vr_preparing': bool(self.vr_waypoints),
                'vr_grab_radians': self.spec['vrGrabRadians'], 'revision': self.revision, 'sequence': self.sequence, 'joints': self.data.qpos[self.qadr].tolist(),
                'velocities': self.data.qvel[self.dadr].tolist(), 'target_joints': self.target.tolist(),
                'gripper': float(np.mean(self.data.qpos[self.fadr])/.05*100),
                'target_gripper': self.gripper, 'tcp': self._pose(self.data),
                'mode': self.mode, 'running': self.running, 'collision_protection': self.protection,
                'contacts': self._contacts(self.data), 'blocked_contacts': self.blocked,
                'obstacle': self.obstacle, 'simulation_time': float(self.data.time),
                'fault': self.fault, 'command_count': self.command_count,
                'engine': 'MuJoCo ' + mujoco.__version__, 'speed_rad_s': self.speed,
                'ik_position_tolerance_mm': self.ik_position_tolerance_mm,
                'ik_orientation_tolerance_deg': self.ik_orientation_tolerance_deg,
                'tcp_note': '6_Link + [0.1,0,0] m，模型参考 TCP，未做真机标定',
                'obstacle_box': {'position': [.30, .16, .20], 'size': [.10, .10, .20]}}

    def state(self):
        with self.lock:
            return self._snapshot()

    def command(self, payload):
        if not isinstance(payload, dict):
            raise CommandError('INVALID_INPUT', '请求必须是 JSON 对象')
        with self.lock:
            kind = payload.get('type')
            if 'expected_revision' in payload:
                expected = payload['expected_revision']
                if type(expected) is not int or expected != self.revision:
                    raise CommandError('CONTROL_CHANGED', '仿真状态已被其他操作修改，VR 跟随已停止，请重新启用')
            if self.vr_waypoints and kind not in ('pause', 'reset', 'vr_exit'):
                raise CommandError('VR_PREPARING', '正在移动到 VR 抓取位姿，请等待或暂停')
            if kind in ('joints', 'pose'):
                q = self.target.copy()
                errors = None
                if kind == 'joints':
                    q = vector(payload.get('joints'), 6, 'joints（弧度）')
                    if np.any(q < self.limits[:, 0]-1e-9) or np.any(q > self.limits[:, 1]+1e-9):
                        raise CommandError('JOINT_LIMIT', '关节目标超出模型限位')
                else:
                    if payload.get('frame', 'base') != 'base':
                        raise CommandError('INVALID_INPUT', '目标位姿必须使用 base 坐标系')
                    if 'position_only' in payload and type(payload['position_only']) is not bool:
                        raise CommandError('INVALID_INPUT', 'position_only 必须为布尔值')
                    q, errors = self._ik(payload.get('position'), payload.get('quaternion'),
                                         payload.get('position_only', False) is True)
                    if 'expected_revision' in payload and np.max(np.abs(q-self.target)) > np.deg2rad(20):
                        raise CommandError('IK_BRANCH_JUMP', '零位或奇异位置附近逆解跳变过大，保持当前姿态；请先小幅向上移动再展开')
                try:
                    grip = float(payload.get('gripper', self.gripper))
                except (ValueError, TypeError) as error:
                    raise CommandError('INVALID_INPUT', 'gripper 必须为 0–100') from error
                if not np.isfinite(grip) or not 0 <= grip <= 100:
                    raise CommandError('INVALID_INPUT', 'gripper 必须为 0–100')
                start = self.data.qpos[self.qadr].copy()
                actual_grip = np.mean(self.data.qpos[self.fadr])/.05*100
                contacts = self._check_path(start, q, actual_grip, grip)
                if contacts and self.protection:
                    self.blocked = contacts
                    raise CommandError('COLLISION', '目标或关节插值路径存在碰撞，已拒绝目标', contacts)
                self.target, self.gripper = q.copy(), grip
                self.blocked, self.fault = [], ''
                if self.mode == 'kinematic':
                    self._put(self.data, self.target, self.gripper)
                    self.servo = self.target.copy()
                self.command_count += 1
                self.last_command = time.monotonic()
                self.revision += 1
                result = self._snapshot()
                result['ik_residual'] = errors
                return result
            if kind == 'vr_enter' or (kind == 'reset' and self.vr_mode):
                if self.mode != 'kinematic':
                    raise CommandError('INVALID_MODE', 'VR 准备仅支持运动学模式')
                home = np.array(self.spec['vrGrabRadians'], dtype=float)
                waypoints = [np.zeros(6), home] if kind == 'vr_enter' else [home]
                start = self.data.qpos[self.qadr].copy()
                opening = float(np.mean(self.data.qpos[self.fadr])/.05*100)
                for end in waypoints:
                    contacts = self._check_path(start, end, opening, self.DEFAULT_GRIPPER)
                    if contacts and self.protection:
                        raise CommandError('COLLISION', 'VR 准备路径存在碰撞，已取消', contacts)
                    start = end
                    opening = self.DEFAULT_GRIPPER
                self.running = False
                self.vr_mode = True
                self.vr_waypoints = waypoints
                self.vr_gripper_target = self.DEFAULT_GRIPPER
                self.blocked, self.fault = [], ''
            elif kind == 'vr_exit':
                # Stop the current motion before planning the bounded return to zero.
                self.vr_mode = False
                self.vr_waypoints = []
                self.running = False
                current = self.data.qpos[self.qadr].copy()
                self.target, self.servo = current.copy(), current.copy()
                goal = np.zeros(6)
                contacts = self._check_path(current, goal, self.gripper, self.gripper)
                if contacts and self.protection:
                    self.blocked = contacts
                    self.fault = '回零路径存在碰撞，已停止'
                    raise CommandError('COLLISION', self.fault, contacts)
                self.vr_waypoints = [goal]
                self.vr_gripper_target = self.gripper
                self.blocked, self.fault = [], ''
            elif kind == 'settings':
                mode = payload.get('mode', self.mode)
                if mode not in ('kinematic', 'dynamic'):
                    raise CommandError('INVALID_INPUT', 'mode 必须为 kinematic 或 dynamic')
                for name in ('collision_protection', 'obstacle'):
                    if name in payload and type(payload[name]) is not bool:
                        raise CommandError('INVALID_INPUT', name + ' 必须为布尔值')
                try:
                    settings = validate_simulation({
                        'speed_rad_s': self.speed,
                        'ik_position_tolerance_mm': self.ik_position_tolerance_mm,
                        'ik_orientation_tolerance_deg': self.ik_orientation_tolerance_deg,
                        **{key: payload[key] for key in ('speed_rad_s', 'ik_position_tolerance_mm', 'ik_orientation_tolerance_deg') if key in payload},
                    })
                except ValueError as error:
                    raise CommandError('INVALID_INPUT', str(error)) from error
                self.speed = settings['speed_rad_s']
                self.ik_position_tolerance_mm = settings['ik_position_tolerance_mm']
                self.ik_orientation_tolerance_deg = settings['ik_orientation_tolerance_deg']
                self.protection = payload.get('collision_protection', self.protection)
                self.obstacle = payload.get('obstacle', self.obstacle)
                self.model.geom_contype[self.obstacle_id] = int(self.obstacle)
                self.model.geom_conaffinity[self.obstacle_id] = int(self.obstacle)
                if mode != self.mode:
                    self.mode = mode
                    self.running = False
                    self.data.qvel[:] = 0
                    self.target = self.data.qpos[self.qadr].copy()
                    self.servo = self.target.copy()
                mujoco.mj_forward(self.model, self.data)
                self.blocked, self.fault = [], ''
            elif kind == 'resume':
                if self.mode != 'dynamic':
                    raise CommandError('INVALID_MODE', '请先切换到动力学模式')
                contacts = self._contacts(self.data)
                if contacts and self.protection:
                    raise CommandError('COLLISION', '当前姿态存在碰撞，不能开始动力学', contacts)
                self.fault = ''
                self.running = True
            elif kind == 'pause':
                self.vr_waypoints = []
                self.running = False
                self.data.qvel[:] = 0
                self.target = self.data.qpos[self.qadr].copy()
                self.servo = self.target.copy()
                mujoco.mj_forward(self.model, self.data)
            elif kind == 'reset':
                self.running = False
                self.target = np.array(self.spec['homeRadians'])
                self.servo = self.target.copy()
                self.gripper = self.DEFAULT_GRIPPER
                mujoco.mj_resetData(self.model, self.data)
                self._put(self.data, self.target, self.gripper)
                self.blocked, self.fault = [], ''
            else:
                raise CommandError('INVALID_INPUT', '未知命令 type')
            self.revision += 1
            return self._snapshot()

    def step(self, steps=5):
        with self.lock:
            if self.vr_waypoints:
                current = self.data.qpos[self.qadr].copy()
                goal = self.vr_waypoints[0]
                delta = goal-current
                current_grip = float(np.mean(self.data.qpos[self.fadr])/.05*100)
                grip_delta = self.vr_gripper_target-current_grip
                # Shared interpolation completes both arm and fingers; at most
                # 0.5 rad/s for joints and 50 percentage points/s for the gripper.
                duration = max(np.max(np.abs(delta))/.5, abs(grip_delta)/50., 1e-12)
                fraction = min(1., steps*.002/duration)
                q = current+fraction*delta
                opening = current_grip+fraction*grip_delta
                contacts = self._check_path(current, q, current_grip, opening)
                if contacts and self.protection:
                    self.vr_waypoints = []
                    self.blocked = contacts
                    self.fault = 'VR 准备遇到碰撞，已停止'
                else:
                    self._put(self.data, q, opening)
                    self.gripper = opening
                    self.target, self.servo = q.copy(), q.copy()
                    if fraction == 1.: self.vr_waypoints.pop(0)
                self.revision += 1
                return
            if self.mode != 'dynamic' or not self.running:
                return
            kp = np.array([45, 80, 60, 12, 8, 3.])
            kd = np.array([1, 2.5, 1.3, .15, .08, .03])
            for _ in range(steps):
                previous = self.data.qpos.copy()
                self.servo += np.clip(self.target-self.servo, -self.speed*.002, self.speed*.002)
                torque = kp*(self.servo-self.data.qpos[self.qadr]) - kd*self.data.qvel[self.dadr]
                torque += self.data.qfrc_bias[self.dadr]
                self.data.ctrl[:6] = np.clip(torque, self.model.actuator_ctrlrange[:6, 0], self.model.actuator_ctrlrange[:6, 1])
                left = self.fadr[0]
                self.data.ctrl[6] = np.clip(100*(self.gripper*.0005-self.data.qpos[left]) - self.data.qvel[left], -3, 3)
                mujoco.mj_step(self.model, self.data)
                mujoco.mj_forward(self.model, self.data)
                contacts = self._contacts(self.data)
                invalid = not np.all(np.isfinite(self.data.qpos)) or np.max(np.abs(self.data.qvel)) > 30
                if invalid or (contacts and self.protection):
                    self.data.qpos[:] = previous
                    self.data.qvel[:] = 0
                    mujoco.mj_forward(self.model, self.data)
                    self.running = False
                    self.target = self.data.qpos[self.qadr].copy()
                    self.servo = self.target.copy()
                    self.blocked = contacts
                    self.fault = '动力学数值异常，已暂停' if invalid else '动力学接触触发碰撞拦截，已暂停'
                    break

    def _run(self):
        while not self.closed.is_set():
            start = time.monotonic()
            try:
                self.step(5)
            except Exception as error:
                with self.lock:
                    self.running = False
                    self.fault = f'动力学异常，已暂停：{error}'
            self.closed.wait(max(0, .01-(time.monotonic()-start)))
