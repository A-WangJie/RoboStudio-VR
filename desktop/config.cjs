const fs = require('node:fs');
const path = require('node:path');

const defaults = {version: 1, pythonPath: '', simulation: {
  speed_rad_s: .6, ik_position_tolerance_mm: .5,
  ik_orientation_tolerance_deg: 1, collision_protection: true, obstacle: false,
}};

function validateSettings(input) {
  if (!input || input.version !== 1 || typeof input.pythonPath !== 'string') throw new Error('配置版本或 Python 路径无效');
  const sim = input.simulation;
  if (!sim || typeof sim !== 'object') throw new Error('缺少仿真设置');
  for (const [key, min, max] of [['speed_rad_s', .01, 2], ['ik_position_tolerance_mm', .01, 5], ['ik_orientation_tolerance_deg', .01, 10]]) {
    if (!Number.isFinite(sim[key]) || sim[key] < min || sim[key] > max) throw new Error(`${key} 必须在 ${min}–${max} 之间`);
  }
  for (const key of ['collision_protection', 'obstacle']) if (typeof sim[key] !== 'boolean') throw new Error(`${key} 必须为布尔值`);
  return {version: 1, pythonPath: input.pythonPath.trim(), simulation: Object.fromEntries(Object.keys(defaults.simulation).map(key => [key, sim[key]]))};
}

function atomicJSON(filename, value) {
  fs.mkdirSync(path.dirname(filename), {recursive: true});
  const temp = `${filename}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temp, JSON.stringify(value, null, 2) + '\n', {mode: 0o600});
    fs.renameSync(temp, filename);
  } finally { if (fs.existsSync(temp)) fs.unlinkSync(temp); }
}

function readSettings(filename) {
  if (!fs.existsSync(filename)) atomicJSON(filename, defaults);
  return validateSettings(JSON.parse(fs.readFileSync(filename, 'utf8')));
}

function validateWorkspace(input) {
  if (!input || input.format !== 's1-studio-workspace' || input.version !== 1 || input.robot !== 's1_v1') throw new Error('不是受支持的 S1 V1 工作区文件');
  const array = (value, count) => Array.isArray(value) && value.length === count && value.every(Number.isFinite);
  if (!array(input.joints, 6) || !Number.isFinite(input.gripper) || input.gripper < 0 || input.gripper > 100) throw new Error('工作区关节或夹爪数据无效');
  if (!array(input.camera?.position, 3) || !array(input.camera?.target, 3) || [...input.camera.position, ...input.camera.target].some(value => Math.abs(value) > 100)) throw new Error('工作区视角数据无效');
  if (Math.hypot(...input.camera.position.map((value, i) => value - input.camera.target[i])) < .05) throw new Error('工作区相机与观察点过近');
  if (typeof input.obstacle !== 'boolean') throw new Error('工作区障碍物设置无效');
  return {format: input.format, version: 1, robot: 's1_v1', joints: [...input.joints], gripper: input.gripper,
    camera: {position: [...input.camera.position], target: [...input.camera.target]}, obstacle: input.obstacle};
}

function validateProjectShortcuts(value) {
  if (!Array.isArray(value) || value.length > 128 || value.some(route =>
    typeof route !== 'string' || route.length > 160 || !/^[a-z0-9-]+(?:\/[a-z0-9-]+){0,5}$/.test(route))) {
    throw new Error('快捷目标栏设置无效');
  }
  return [...new Set(value)];
}

module.exports = {defaults, validateSettings, readSettings, atomicJSON, validateWorkspace, validateProjectShortcuts};
