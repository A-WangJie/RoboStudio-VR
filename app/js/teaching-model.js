// Configuration and offline joint mapping; no robot transport is opened here.
export function defaultTeachingConfig() {
  return {rateHz: 30, timeoutMs: 250, gripper: true, holdToEnable: true,
    pairs: ['A', 'B'].map((follower, i) => ({follower, enabled: true,
      leader: {label: `主臂 ${follower}`, device: '', bitrate: null},
      direction: [1,1,1,1,1,1], scale: [1,1,1,1,1,1], offsetDegrees: [0,0,0,0,0,0],
      alignmentConfirmed: false}))};
}

export function validateTeachingConfig(value, connection, arms) {
  const fail = message => {throw new Error(message);};
  const number = (v, min, max, label) => {
    if (!Number.isFinite(v) || v < min || v > max) fail(`${label}应为 ${min}–${max} 之间的数值`);
  };
  if (!value || value.holdToEnable !== true) fail('主从示教必须保留按住使能');
  number(value.rateHz, 1, 100, '示教频率（Hz）');
  number(value.timeoutMs, 100, 5000, '主臂输入超时（ms）');
  if (!Number.isInteger(value.rateHz) || !Number.isInteger(value.timeoutMs)) fail('示教频率和超时应为整数');
  if (value.timeoutMs < 1000 / value.rateHz) fail('输入超时不能小于一个示教采样周期');
  if (typeof value.gripper !== 'boolean') fail('夹爪跟随格式无效');
  if (!Array.isArray(value.pairs) || value.pairs.length !== 2) fail('示教配置需要 A、B 两组主从配对');
  const pairs = value.pairs.map((pair, i) => {
    if (!pair || pair.follower !== ['A','B'][i]) fail('从臂配对标识无效');
    if (typeof pair.enabled !== 'boolean' || typeof pair.alignmentConfirmed !== 'boolean') fail('示教通道选项格式无效');
    const leader = pair.leader;
    if (!leader || typeof leader.label !== 'string' || !leader.label.trim() || leader.label.trim().length > 40) fail('主臂名称应为 1–40 个字符');
    if (typeof leader.device !== 'string' || (leader.device && !/^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}$/.test(leader.device))) fail('主臂 CAN 接口名称无效');
    if (leader.bitrate !== null) {
      number(leader.bitrate, 10000, 1000000, '主臂 CAN 速率');
      if (!Number.isInteger(leader.bitrate)) fail('主臂 CAN 速率应为整数');
    }
    for (const [key, min, max] of [['direction',-1,1],['scale',.1,2],['offsetDegrees',-180,180]]) {
      if (!Array.isArray(pair[key]) || pair[key].length !== 6) fail('主从关节映射需要六个参数');
      pair[key].forEach((v, j) => {
        number(v, min, max, `通道 ${pair.follower} / J${j+1}`);
        if (key === 'direction' && ![1,-1].includes(v)) fail('关节方向仅支持同向或反向');
      });
    }
    return {follower: pair.follower, enabled: pair.enabled,
      leader: {label: leader.label.trim(), device: leader.device, bitrate: leader.bitrate},
      direction: [...pair.direction], scale: [...pair.scale], offsetDegrees: [...pair.offsetDegrees],
      alignmentConfirmed: pair.alignmentConfirmed};
  });
  const activeArms = connection.layout === 'single' ? arms.slice(0,1) : arms;
  const occupied = new Set(activeArms.map(arm => arm.device));
  for (const pair of pairs.slice(0, connection.layout === 'single' ? 1 : 2).filter(pair => pair.enabled)) {
    if (!pair.leader.device) continue;
    if (occupied.has(pair.leader.device)) fail(`主臂 ${pair.follower} 接口与其他主臂或从臂重复`);
    occupied.add(pair.leader.device);
  }
  return {rateHz: value.rateHz, timeoutMs: value.timeoutMs, gripper: value.gripper, holdToEnable: true, pairs};
}

export function mapTeachingJoints(pair, leaderDegrees, limits) {
  if (!Array.isArray(leaderDegrees) || leaderDegrees.length !== 6 || !leaderDegrees.every(Number.isFinite)) throw new Error('请输入六个有效的主臂角度');
  const target = leaderDegrees.map((angle, j) => angle * pair.direction[j] * pair.scale[j] + pair.offsetDegrees[j]);
  const violations = target.flatMap((angle, j) => angle < limits[j][0] || angle > limits[j][1] ? [`J${j+1}`] : []);
  return {target, violations};
}
