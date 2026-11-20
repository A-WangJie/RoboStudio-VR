// Offline configuration only. This module never loads the SDK or accesses a bus.
import {defaultTeachingConfig, validateTeachingConfig} from './teaching-model.js';
export const SDK_REFERENCE = '14-DOF robotic arm/S1_SDK_V2';
export const JOINT_LIMITS = [[-170, 170], [0, 179.9], [0, 170], [-89.9, 86.9], [-89.9, 89.9], [-89.9, 89.9]];
export const defaultXRConnection = () => ({device: 'quest', transport: 'wifi', host: '', port: 8766, serial: '', autoReconnect: false});
export function defaultArmConfig() {
  return {version: 1, model: 's1_v1', connection: {layout: 'auto', autoDetect: true, timeoutMs: 2000},
    arms: ['A', 'B'].map((id, i) => ({id, label: `机械臂 ${id}`, device: `can${i}`, bitrate: null,
      endEffector: 'gripper', checkCollision: true, resetDegrees: null, resetSpeed: 5,
      arSource: 'unassigned', positionScale: 1, basePose: [0, 0, 0, 0, 0, 0], tcpOffset: [0, 0, 0],
      calibrationConfirmed: false})),
    teaching: defaultTeachingConfig(),
    startup: {readState: true, checkLimits: true, requireEnable: true},
    ar: {holdToEnable: true, timeoutMs: 500, connection: defaultXRConnection()}};
}
export function validateArmConfig(value) {
  const fail = message => {throw new Error(message);};
  const number = (v, min, max, label) => {if (!Number.isFinite(v) || v < min || v > max) fail(`${label}应为 ${min}–${max} 之间的数值`);};
  const bool = (v, label) => {if (typeof v !== 'boolean') fail(`${label}格式无效`);};
  if (!value || value.version !== 1 || value.model !== 's1_v1') fail('只支持 S1 V1 配置版本 1');
  const c = value.connection;
  if (!c || !['auto', 'single', 'dual'].includes(c.layout)) fail('机械臂数量模式无效');
  bool(c.autoDetect, '自动检测'); number(c.timeoutMs, 100, 30000, '连接超时（ms）');
  if (!Number.isInteger(c.timeoutMs)) fail('连接超时（ms）应为整数');
  if (!Array.isArray(value.arms) || value.arms.length !== 2) fail('配置必须包含 A、B 两个设备槽位');
  const arms = value.arms.map((a, i) => {
    if (!a || a.id !== ['A', 'B'][i]) fail('设备槽位标识无效');
    if (typeof a.label !== 'string' || !a.label.trim() || a.label.trim().length > 40) fail(`机械臂 ${a.id} 名称应为 1–40 个字符`);
    if (typeof a.device !== 'string' || !/^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}$/.test(a.device)) fail(`机械臂 ${a.id} 的 CAN 接口名称无效`);
    if (a.bitrate !== null) {number(a.bitrate, 10000, 1000000, 'CAN 速率（bit/s）'); if (!Number.isInteger(a.bitrate)) fail('CAN 速率应为整数');}
    if (!['None', 'gripper'].includes(a.endEffector)) fail('末端仅支持无末端或平行夹爪');
    bool(a.checkCollision, '自碰撞检查'); bool(a.calibrationConfirmed, '坐标标定确认');
    number(a.resetSpeed, .1, 30, '复位速度（°/s，工作台配置范围）');
    if (a.resetDegrees !== null) {
      if (!Array.isArray(a.resetDegrees) || a.resetDegrees.length !== 6) fail('复位目标需要六个关节角');
      a.resetDegrees.forEach((v, j) => number(v, ...JOINT_LIMITS[j], `${a.id} / J${j + 1} 复位角度`));
    }
    if (!['unassigned', 'left', 'right'].includes(a.arSource)) fail('AR 输入分配无效');
    number(a.positionScale, .05, 2, '位置比例');
    for (const [key, count, max] of [['basePose', 6, 10000], ['tcpOffset', 3, 1000]]) {
      if (!Array.isArray(a[key]) || a[key].length !== count) fail('坐标参数数量无效');
      a[key].forEach((v, j) => number(v, key === 'basePose' && j > 2 ? -180 : -max, key === 'basePose' && j > 2 ? 180 : max, '坐标参数'));
    }
    return {id:a.id, label:a.label.trim(), device:a.device, bitrate:a.bitrate, endEffector:a.endEffector,
      checkCollision:a.checkCollision, resetDegrees:a.resetDegrees === null ? null : [...a.resetDegrees], resetSpeed:a.resetSpeed,
      arSource:a.arSource, positionScale:a.positionScale, basePose:[...a.basePose], tcpOffset:[...a.tcpOffset], calibrationConfirmed:a.calibrationConfirmed};
  });
  if (c.layout !== 'single' && arms[0].device === arms[1].device) fail('双臂或自动识别模式下，A、B 不能使用同一个 CAN 接口');
  if (c.layout !== 'single' && arms[0].arSource !== 'unassigned' && arms[0].arSource === arms[1].arSource) fail('两台机械臂不能分配到同一个 AR 输入');
  const startup = value.startup;
  if (!startup || startup.requireEnable !== true) fail('必须保留人工使能确认');
  bool(startup.readState, '初始状态读取'); bool(startup.checkLimits, '初始限位核对');
  if (!value.ar || value.ar.holdToEnable !== true) fail('AR 控制必须保留按住使能');
  number(value.ar.timeoutMs, 100, 5000, 'AR 超时（ms）');
  // Existing version-1 files retain pairings and gain only the new connection defaults.
  const xr = value.ar.connection === undefined ? defaultXRConnection() : value.ar.connection;
  if (!xr || !['quest','openxr'].includes(xr.device) || !['wifi','usb'].includes(xr.transport)) fail('VR 设备或连接方式无效');
  if (typeof xr.host !== 'string' || xr.host.length > 253 || (xr.host && !/^[a-zA-Z0-9][a-zA-Z0-9.-]*$/.test(xr.host))) fail('桥接主机请填写 IPv4 地址或主机名，不含协议和路径');
  number(xr.port, 1024, 65535, '桥接端口');
  if (!Number.isInteger(xr.port)) fail('桥接端口必须为整数');
  if (typeof xr.serial !== 'string' || xr.serial.length > 80 || (xr.serial && !/^[a-zA-Z0-9_.:-]+$/.test(xr.serial))) fail('设备序列号格式无效');
  bool(xr.autoReconnect, 'VR 自动重连');
  const teaching = validateTeachingConfig(value.teaching === undefined ? defaultTeachingConfig() : value.teaching, c, arms);
  return {version:1, model:'s1_v1', connection:{layout:c.layout, autoDetect:c.autoDetect, timeoutMs:c.timeoutMs}, arms,
    teaching,
    startup:{readState:startup.readState, checkLimits:startup.checkLimits, requireEnable:true}, ar:{holdToEnable:true, timeoutMs:value.ar.timeoutMs,
      connection:{device:xr.device, transport:xr.transport, host:xr.host, port:xr.port, serial:xr.serial, autoReconnect:xr.autoReconnect}}};
}
export function readinessNotes(config, context = 'all') {
  const arms = config.connection.layout === 'single' ? config.arms.slice(0, 1) : config.arms;
  const notes = arms.flatMap(a => [a.bitrate === null && `${a.label}：CAN 速率待确认`, a.resetDegrees === null && `${a.label}：复位目标未设置`,
    context !== 'teaching' && a.arSource === 'unassigned' && `${a.label}：AR 输入未分配`, !a.calibrationConfirmed && `${a.label}：基座 / TCP 坐标尚未标定`].filter(Boolean));
  if (context === 'teaching') {
    const pairs = config.teaching.pairs.slice(0, config.connection.layout === 'single' ? 1 : 2).filter(p => p.enabled);
    if (!pairs.length) notes.push('尚未选择参与示教的通道');
    for (const pair of pairs) {
      if (!pair.leader.device) notes.push(`主臂 ${pair.follower}：CAN 接口未设置`);
      if (pair.leader.bitrate === null) notes.push(`主臂 ${pair.follower}：CAN 速率待确认`);
      if (!pair.alignmentConfirmed) notes.push(`通道 ${pair.follower}：主从起始姿态尚未核对`);
    }
  }
  return notes;
}
