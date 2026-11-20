const fs = require('node:fs');
const path = require('node:path');
const {runtimePaths} = require('./paths.cjs');
function choosePython(root, settings = {}, env = process.env) {
  if (env.S1_STUDIO_PYTHON) return env.S1_STUDIO_PYTHON;
  if (settings.pythonPath) return settings.pythonPath;
  const filename = path.join(runtimePaths(root, env).config, 'runtime.json');
  if (fs.existsSync(filename)) {
    const local = JSON.parse(fs.readFileSync(filename, 'utf8'));
    if (local.pythonPath) return local.pythonPath;
  }
  const venv = path.join(root, '.venv/bin/python');
  return fs.existsSync(venv) ? venv : 'python3';
}
module.exports = {choosePython};
