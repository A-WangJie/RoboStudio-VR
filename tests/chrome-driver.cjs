// Real-time Chrome CDP driver using Node's built-in WebSocket, no npm dependencies.
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const [chrome, profile, url, screenshot, output] = process.argv.slice(2);
fs.mkdirSync(path.dirname(output), {recursive: true});
if (screenshot !== '-') fs.mkdirSync(path.dirname(screenshot), {recursive: true});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const child = spawn(chrome, ['--headless', `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--use-angle=swiftshader', '--disable-dev-shm-usage',
  '--window-size=1600,1100', '--remote-debugging-port=0', url], {detached: true, stdio: ['ignore', 'ignore', 'pipe']});
let socket, stderr = '', nextId = 0;
const pending = new Map();
child.stderr.on('data', bytes => {stderr = (stderr + bytes).slice(-6000);});
child.on('error', error => {stderr += error.message;});
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => {pending.delete(id); reject(new Error(`CDP timeout: ${method}`));}, 10000);
    pending.set(id, {resolve, reject, timer});
    socket.send(JSON.stringify({id, method, params}));
  });
}

(async () => {
  const deadline = Date.now() + 35000;
  const activePort = path.join(profile, 'DevToolsActivePort');
  while (!fs.existsSync(activePort)) {
    if (Date.now() > deadline || child.exitCode !== null) throw new Error('Chrome did not start: ' + stderr);
    await delay(50);
  }
  const port = fs.readFileSync(activePort, 'utf8').split('\n')[0];
  let target;
  while (!target) {
    target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(page => page.type === 'page');
    if (Date.now() > deadline) throw new Error('Chrome page unavailable');
    if (!target) await delay(50);
  }
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {socket.addEventListener('open', resolve, {once: true}); socket.addEventListener('error', reject, {once: true});});
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id); clearTimeout(request.timer);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });
  let result;
  while (Date.now() < deadline) {
    try {
      const evaluation = await call('Runtime.evaluate', {expression: 'document.getElementById("test-result")?.textContent', returnByValue: true});
      if (evaluation.result.value) {result = JSON.parse(evaluation.result.value); break;}
    } catch (error) {if (!error.message.includes('context')) throw error;}
    await delay(100);
  }
  if (!result) {
    const evaluation = await call('Runtime.evaluate', {expression: 'document.documentElement.outerHTML', returnByValue: true});
    fs.writeFileSync(output + '.html', evaluation.result.value);
    throw new Error('Browser driver did not finish; see ' + output + '.html');
  }
  fs.writeFileSync(output, JSON.stringify(result, null, 2));
  if (screenshot !== '-') {
    const capture = await call('Page.captureScreenshot', {format: 'png', fromSurface: true});
    fs.writeFileSync(screenshot, Buffer.from(capture.data, 'base64'));
  }
})().catch(error => {console.error(error.stack + '\n' + stderr); process.exitCode = 1;}).finally(async () => {
  for (const request of pending.values()) clearTimeout(request.timer);
  socket?.close();
  try {process.kill(-child.pid, 'SIGTERM');} catch (error) {if (error.code !== 'ESRCH') throw error;}
});
