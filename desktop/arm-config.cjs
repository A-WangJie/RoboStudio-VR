const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {atomicJSON} = require('./config.cjs');
const model = import(pathToFileURL(path.join(__dirname, '../app/js/arm-config-model.js')).href);

// No SDK imports, process spawning, interface enumeration, or robot commands.
async function readArmConfig(filename) {
  const {defaultArmConfig, validateArmConfig} = await model;
  return {config: fs.existsSync(filename) ? validateArmConfig(JSON.parse(fs.readFileSync(filename, 'utf8'))) : defaultArmConfig(), path: filename, exists: fs.existsSync(filename)};
}
async function saveArmConfig(filename, value) {
  const {validateArmConfig} = await model;
  const config = validateArmConfig(value);
  atomicJSON(filename, config);
  return {config, path: filename, exists: fs.existsSync(filename)};
}
module.exports = {readArmConfig, saveArmConfig};
