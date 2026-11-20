import * as THREE from 'three';
import { TransformControls } from '../vendor/TransformControls.js';
import { MouseFollow } from './mouse-follow.js';

const $ = selector => document.querySelector(selector);
const deg = THREE.MathUtils.radToDeg;

export class Teleop {
  constructor({ state, robot, viewport }) {
    Object.assign(this, { state, robot, viewport });
    this.ready = false;
    this.pending = null;
    this.commands = [];
    this.completions = new WeakMap();
    this.stopPending = false;
    this.connectedOnce = false;
    this.busy = false;
    this.snapshot = null;
    this.target = new THREE.Object3D();
    this.target.name = '末端目标';
    viewport.scene.add(this.target);
    this.drag = new TransformControls(viewport.camera, viewport.renderer.domElement);
    this.drag.setSize(.75);
    this.drag.setSpace('world');
    this.helper = this.drag.getHelper();
    this.helper.visible = false;
    viewport.scene.add(this.helper);
    this.drag.addEventListener('dragging-changed', event => {
      viewport.controls.enabled = !event.value;
      if (!event.value && this.drag.enabled) this.queuePose();
    });
    this.drag.addEventListener('objectChange', () => {
      this.writePose(this.target.position.toArray(), this.target.quaternion.toArray());
      this.queuePose();
      viewport.invalidate();
    });
    this.drag.addEventListener('change', () => viewport.invalidate());
    this.marker = new THREE.AxesHelper(.085);
    this.target.add(this.marker);
    this.marker.visible = false;
    this.obstacle = new THREE.Mesh(new THREE.BoxGeometry(.10, .10, .20),
      new THREE.MeshStandardMaterial({ color: '#c58a4e', roughness: .7 }));
    this.obstacle.position.set(.30, .16, .20);
    this.obstacle.visible = false;
    this.obstacle.castShadow = true;
    viewport.scene.add(this.obstacle);
    this.mouse = new MouseFollow(this);
    this.bind();
  }

  bind() {
    ['joint', 'pose'].forEach(name => $(`#${name}-tab`).addEventListener('click', () => {
      ['joint', 'pose'].forEach(other => {
        $(`#${other}-panel`).hidden = other !== name;
        $(`#${other}-tab`).setAttribute('aria-selected', String(other === name));
      });
    }));
    $('#simulation-mode').addEventListener('change', event => this.send({ type: 'settings', mode: event.target.value }));
    $('#collision-protection').addEventListener('change', event => this.send({ type: 'settings', collision_protection: event.target.checked }));
    $('#obstacle-enabled').addEventListener('change', event => this.send({ type: 'settings', obstacle: event.target.checked }));
    $('#simulation-run').addEventListener('click', () => this.send({ type: 'resume' }));
    $('#simulation-pause').addEventListener('click', () => { this.pending = null; this.send({ type: 'pause' }); });
    $('#simulation-reset').addEventListener('click', () => { this.pending = null; this.send({ type: 'reset' }); });
    $('#pose-sync').addEventListener('click', () => this.syncTarget());
    $('#pose-apply').addEventListener('click', () => {
      const position = ['x', 'y', 'z'].map(axis => $(`#pose-${axis}`).valueAsNumber / 1000);
      const rpy = ['roll', 'pitch', 'yaw'].map(axis => THREE.MathUtils.degToRad($(`#pose-${axis}`).valueAsNumber));
      if (![...position, ...rpy].every(Number.isFinite)) { this.message('请输入完整的有限数值'); return; }
      // URDF fixed-axis RPY is Rz(yaw) Ry(pitch) Rx(roll), Three's ZYX Euler.
      const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(...rpy, 'ZYX'));
      this.target.position.fromArray(position);
      this.target.quaternion.copy(quaternion);
      this.queuePose();
    });
    $('#drag-toggle').addEventListener('click', () => {
      const enabled = $('#drag-toggle').getAttribute('aria-pressed') !== 'true';
      $('#drag-toggle').setAttribute('aria-pressed', String(enabled));
      $('#drag-toggle').textContent = enabled ? '关闭末端拖拽' : '开启末端拖拽';
      if (enabled) this.syncTarget();
      this.mouse.update();
      this.viewport.invalidate();
    });
    $('#drag-mode').addEventListener('change', () => {this.mouse.update();this.syncTarget();});
    $('#follow-behavior').addEventListener('change', () => this.mouse.update());
  }

  async request(path, body) {
    let response;
    try {
      response = await fetch(path, { signal: AbortSignal.timeout(5000), ...(body ? {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      } : {}) });
    } catch (error) { throw Object.assign(error, { transport: true }); }
    const result = await response.json().catch(() => ({ message: `HTTP ${response.status}` }));
    if (!response.ok) throw Object.assign(new Error(result.message || `HTTP ${response.status}`), result);
    return result;
  }

  async connect() {
    try {
      const snapshot = await this.request('/api/sim/state');
      this.ready = true;
      this.connectedOnce = true;
      this.setEnabled(true);
      this.apply(snapshot);
      this.syncTarget();
      this.timer = setInterval(() => this.poll(), 70);
    } catch (error) {
      this.setEnabled(false);
      $('#backend-state').textContent = '未连接';
      $('#collision-state').textContent = '碰撞检测未启用';
      $('#simulation-message').textContent = error.message;
      this.message('MuJoCo 后端未连接；请使用 start-studio.sh 启动');
      $('#simulation-running').textContent = '仅本地模型预览';
    }
  }

  setEnabled(enabled) {
    document.querySelectorAll('.simulation-panel button,.simulation-panel input,.simulation-panel select,#pose-panel button,#pose-panel input,#pose-panel select').forEach(element => { element.disabled = !enabled; });
    if (this.viewport.software) {
      $('#drag-toggle').disabled = $('#drag-mode').disabled = true;
      $('#drag-help').textContent = 'Canvas 降级模式暂不支持三维拖拽；可使用上方位姿输入和逆解。';
    }
  }

  disconnect() {
    this.ready = false;
    this.mouse.update();
    this.pending = null;
    this.commands.forEach(payload => this.completions.get(payload)?.({ok: false, message: '后端连接中断'}));
    this.commands = [];
    clearTimeout(this.flushTimer);
    clearInterval(this.timer);
    this.setEnabled(false);
    document.querySelectorAll('#joint-controls input,#home-pose,#vr-grab-pose,#gripper-slider,[data-gripper]').forEach(element => { element.disabled = true; });
    this.drag.detach();
    this.helper.visible = this.marker.visible = false;
    this.viewport.controls.enabled = true;
    this.viewport.invalidate();
    $('#backend-state').textContent = '连接中断';
    $('#backend-state').classList.remove('connected');
    $('#simulation-running').textContent = '状态未知';
    $('#simulation-message').textContent = '显示最后收到的仿真状态；重新连接前已停止发送目标。';
    this.message('后端连接中断，请检查启动终端并刷新页面。', true);
    window.dispatchEvent(new Event('s1:backend-disconnected'));
  }

  async poll() {
    if (this.busy || this.pending || this.polling || document.hidden) return;
    this.polling = true;
    try {
      this.apply(await this.request('/api/sim/state'));
      this.failures = 0;
    } catch (error) {
      this.failures = (this.failures || 0) + 1;
      if (this.failures >= 3) {
        this.disconnect();
      }
    } finally { this.polling = false; }
  }

  joint(index, value) {
    if (!this.ready) return this.connectedOnce ? false : this.state.setJoint(index, value);
    if (this.stopPending) return;
    const q = [...(this.desiredJoints || this.snapshot.target_joints)];
    const [min, max] = this.state.joints[index].limits;
    if (!Number.isFinite(value)) return;
    q[index] = Math.max(min, Math.min(max, value));
    this.desiredJoints = q;
    this.queue({ type: 'joints', joints: q, gripper: this.desiredGripper ?? this.snapshot.target_gripper });
  }

  gripper(value) {
    if(this.hardware?.active&&!this.hardware.gripper){this.message('真机夹爪行程尚未配置，请先填写实际闭合和张开电机角度',true);return;}
    if (!this.ready) return this.connectedOnce ? false : this.state.setGripper(value);
    if (this.stopPending) return;
    this.desiredGripper = Math.max(0, Math.min(100, value));
    // Merge with active Cartesian motion, but do not reuse an idle drag marker:
    // joint controls may have moved the arm since that marker was last synced.
    if (this.mouse.enabled() && (this.mouse.gesture || this.drag.dragging ||
      this.pending?.type === 'pose' || (!this.pending && this.inFlight?.type === 'pose'))) {
      this.queuePose();return;
    }
    this.queue({ type: 'joints', joints: this.desiredJoints || this.snapshot.target_joints, gripper: this.desiredGripper });
  }

  home() {
    if (!this.ready) return this.connectedOnce ? false : this.state.home();
    return this.preset('home');
  }

  async preset(name) {
    if(!this.ready||!['home','vr-grab'].includes(name))return;
    if (this.stopPending) return;
    this.mouse.stop(true);
    this.pending=null;this.desiredJoints=this.desiredGripper=null;
    if(this.hardware?.active){
      const token=this.hardware.token;
      await this.hardware.hold();
      if(!this.hardware.active||this.hardware.token!==token)return;
      this.queue({type:'preset',name});
    }else{
      this.desiredJoints=[...this.state.model[name==='home'?'homeRadians':'vrGrabRadians']];
      this.queue({type:'joints',joints:this.desiredJoints,gripper:name==='vr-grab'?40:this.snapshot.target_gripper});
    }
  }

  queuePose() {
    if (!this.ready) return;
    this.queue({ type: 'pose', frame: 'base', position: this.target.position.toArray(),
      quaternion: this.target.quaternion.toArray(), position_only: $('#position-only').checked,
      gripper: this.desiredGripper ?? this.snapshot.target_gripper });
  }

  queue(payload) {
    if (!this.ready || this.stopPending) return;
    this.pending = payload;
    // Throttle the latest target: continuous mouse events must not postpone it forever.
    if (!this.flushTimer) this.flushTimer = setTimeout(() => {this.flushTimer=null;this.flush();}, 35);
  }

  async flush() {
    if (this.busy || !this.ready) return;
    const payload = this.commands.shift() || this.pending;
    if (!payload) return;
    if (payload === this.pending) this.pending = null;
    const result = await this.execute(payload);
    this.completions.get(payload)?.(result);
    this.completions.delete(payload);
  }

  send(payload) {
    if(this.hardware?.active)return Promise.resolve({ok:false,message:'请先停止真机鼠标控制，再执行仿真或 VR 操作'});
    if (!this.ready) return Promise.resolve({ok: false, message: '后端尚未连接'});
    // Control actions retain their order; a stop discards unsent motion targets.
    if (payload.type === 'pause' || payload.type === 'reset') {
      this.mouse.stop(true);
      this.stopPending = true;
      this.pending = null;
      this.desiredJoints = this.desiredGripper = null;
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    return new Promise(resolve => {
      this.completions.set(payload, resolve);
      this.commands.push(payload);
      this.flush();
    });
  }

  async execute(payload) {
    this.busy = true;
    this.inFlight = payload;
    try {
      const real=this.hardware?.active;
      const result = real ? await this.hardware.control(payload) : await this.request('/api/sim/command', payload);
      this.apply(result);
      if(real)this.message('真机目标已接收 · 限速跟随中，画面显示实际反馈');
      else if (payload.type === 'pose') {
        const error = result.ik_residual;
        this.message(`逆解已应用 · 位置误差 ${error.position_mm.toFixed(3)} mm · 姿态误差 ${error.orientation_deg.toFixed(2)}°`);
      } else this.message({joints: '关节目标已应用', settings: '仿真设置已应用', resume: '动力学仿真已开始', pause: '仿真已暂停', reset: '仿真已重置'}[payload.type] || '操作已完成');
      if (payload.type === 'reset' || payload.type === 'settings') this.syncTarget();
      return {ok: true, state: result};
    } catch (error) {
      console.error('[SIM_COMMAND]', error);
      if (error.transport) { this.disconnect(); return {ok: false, message: '后端连接中断'}; }
      this.message(error.message, true);
      if (this.mouse.gesture) this.mouse.stop(true);
      if (error.contacts?.length) {
        this.robot.highlightContacts(error.contacts);
        $('#collision-state').textContent = '已拦截：' + error.contacts.map(c => c.pair.join(' ↔ ')).join('；');
        $('#collision-state').classList.add('collision-alert');
        this.viewport.invalidate();
      }
      if (!this.drag.dragging) this.syncTarget();
      return {ok: false, message: error.message};
    } finally {
      this.inFlight = null;
      this.busy = false;
      this.stopPending = this.commands.some(command => command.type === 'pause' || command.type === 'reset');
      if (!this.pending) { this.desiredJoints = null; this.desiredGripper = null; }
      this.flush();
    }
  }

  message(text, error = false) {
    $('#pose-result').textContent = text;
    $('#pose-result').classList.toggle('result-error', error);
    window.dispatchEvent(new CustomEvent('s1:notice', {detail: {text, error}}));
  }

  writePose(position, quaternion) {
    ['x', 'y', 'z'].forEach((axis, i) => { $(`#pose-${axis}`).value = (position[i]*1000).toFixed(2); });
    const angles = new THREE.Euler().setFromQuaternion(new THREE.Quaternion().fromArray(quaternion), 'ZYX');
    ['roll', 'pitch', 'yaw'].forEach((axis, i) => { $(`#pose-${axis}`).value = deg([angles.x, angles.y, angles.z][i]).toFixed(2); });
  }

  syncTarget() {
    if (!this.snapshot) return;
    this.target.position.fromArray(this.snapshot.tcp.position);
    this.target.quaternion.fromArray(this.snapshot.tcp.quaternion);
    this.writePose(this.snapshot.tcp.position, this.snapshot.tcp.quaternion);
    this.viewport.invalidate();
  }

  apply(snapshot) {
    if (this.snapshot && snapshot.sequence < this.snapshot.sequence) return;
    const previous = this.snapshot;
    this.snapshot = snapshot;
    const changed = this.state.positions.some((value, i) => Math.abs(value-snapshot.joints[i]) > 1e-7) ||
      Math.abs(this.state.gripper-snapshot.gripper) > 1e-5;
    if (changed) this.state.replace(snapshot.joints, snapshot.gripper);
    $('#backend-state').textContent = snapshot.engine;
    $('#backend-state').classList.add('connected');
    $('#simulation-mode').value = snapshot.mode;
    $('#simulation-running').textContent = snapshot.mode === 'kinematic' ? '运动学' : snapshot.running ? '运行中' : '已暂停';
    $('#simulation-time').textContent = snapshot.simulation_time.toFixed(2);
    $('#simulation-run').disabled = snapshot.mode !== 'dynamic' || snapshot.running;
    $('#simulation-pause').disabled = snapshot.mode !== 'dynamic' || !snapshot.running;
    $('#collision-protection').checked = snapshot.collision_protection;
    $('#obstacle-enabled').checked = snapshot.obstacle;
    this.obstacle.visible = snapshot.obstacle;
    const contacts = snapshot.blocked_contacts.length ? snapshot.blocked_contacts : snapshot.contacts;
    $('#collision-state').textContent = contacts.length ? contacts.map(c => c.pair.join(' ↔ ')).join('；') : snapshot.collision_protection ? '未检测到碰撞 · 拦截开启' : '未检测到碰撞 · 拦截关闭';
    $('#collision-state').classList.toggle('collision-alert', !!contacts.length);
    $('#simulation-message').textContent = snapshot.fault || (snapshot.mode === 'dynamic' ? `重力开启 · 力矩 PD + 重力补偿 · 目标限速 ${snapshot.speed_rad_s} rad/s` : '目标通过逆解和离散路径检查后应用');
    window.dispatchEvent(new CustomEvent('s1:backend-state', {detail: snapshot}));
    const visualChanged = !previous || previous.obstacle !== snapshot.obstacle ||
      JSON.stringify(previous.blocked_contacts.concat(previous.contacts)) !== JSON.stringify(snapshot.blocked_contacts.concat(snapshot.contacts));
    if (visualChanged) {
      this.robot.highlightContacts(contacts);
      this.viewport.invalidate();
    }
  }
}
