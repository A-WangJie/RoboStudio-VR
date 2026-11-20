const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {defaults, validateSettings, readSettings, atomicJSON, validateWorkspace} = require('../desktop/config.cjs');

test('external settings survive rereading and invalid values do not overwrite them', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 's1-config-'));
  try {
    const filename = path.join(directory, 'settings.json');
    const initial = readSettings(filename);
    const next = structuredClone(initial); next.simulation.speed_rad_s = .35;
    atomicJSON(filename, validateSettings(next));
    assert.equal(readSettings(filename).simulation.speed_rad_s, .35);
    for (const bad of [-1, 0, 3, Infinity, NaN, '0.6', true]) {
      next.simulation.speed_rad_s = bad;
      assert.throws(() => validateSettings(next));
      assert.equal(readSettings(filename).simulation.speed_rad_s, .35);
    }
    next.simulation.speed_rad_s = .6; next.simulation.collision_protection = 'false';
    assert.throws(() => validateSettings(next));
    assert.equal(defaults.simulation.speed_rad_s, .6);
  } finally {fs.rmSync(directory, {recursive: true, force: true});}
});

test('workspace rejects wrong robot, non-finite state and degenerate camera', () => {
  const workspace = {format: 's1-studio-workspace', version: 1, robot: 's1_v1', joints: [0,1.05,1.55,.5,0,0], gripper: 40, obstacle: false, camera: {position: [1,-1,1], target: [0,0,.3]}};
  assert.deepEqual(validateWorkspace(workspace), workspace);
  assert.throws(() => validateWorkspace({...workspace, robot: 'dummy'}));
  assert.throws(() => validateWorkspace({...workspace, joints: [NaN,0,0,0,0,0]}));
  assert.throws(() => validateWorkspace({...workspace, camera: {position: [0,0,0], target: [0,0,0]}}));
});
