const path = require('node:path');
const os = require('node:os');
const expand = value => value.startsWith('~/') ? path.join(os.homedir(), value.slice(2)) : value;
function runtimePaths(root, env = process.env) {
  const data = path.resolve(expand(env.S1_STUDIO_DATA_DIR || path.join(root, '.local')));
  return {data,
    config: path.resolve(expand(env.S1_STUDIO_CONFIG_DIR || path.join(data, 'config'))),
    logs: path.resolve(expand(env.S1_STUDIO_LOG_DIR || path.join(root, 'artifacts/logs'))),
    workspaces: path.resolve(expand(env.S1_STUDIO_WORKSPACES_DIR || path.join(data, 'workspaces'))),
    artifacts: path.resolve(expand(env.S1_STUDIO_ARTIFACTS_DIR || path.join(root, 'artifacts'))),
    profile: path.join(data, 'electron')};
}
module.exports = {runtimePaths};
