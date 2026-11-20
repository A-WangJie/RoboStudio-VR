const {spawn} = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const {choosePython} = require('./python.cjs');

class Backend {
  constructor({root, configPath, log, onUnexpectedExit}) {
    Object.assign(this, {root, configPath, log, onUnexpectedExit});
    this.child = null;
    this.url = null;
  }

  start(settings) {
    if (this.child) throw new Error('后端已经启动');
    this.stopping = false;
    const python = choosePython(this.root, settings);
    return new Promise((resolve, reject) => {
      let ready = false;
      const child = this.child = spawn(python, ['-u', path.join(this.root, 'server.py'), '--no-browser', '--port', '0',
        '--config', this.configPath, '--desktop-parent', String(process.pid)], {
        cwd: this.root, stdio: ['ignore', 'pipe', 'pipe'], env: {...process.env, PYTHONUNBUFFERED: '1'},
      });
      this.python = python;
      const timer = setTimeout(() => {
        reject(new Error('MuJoCo 后端启动超时，请检查 Python 环境和日志'));
        child.kill('SIGTERM');
      }, 20000);
      const output = readline.createInterface({input: child.stdout});
      output.on('line', line => {
        this.log('[backend] ' + line);
        if (line.startsWith('S1_BACKEND_READY ')) {
          try {
            const info = JSON.parse(line.slice('S1_BACKEND_READY '.length));
            if (!Number.isInteger(info.port) || info.port < 1 || info.port > 65535) throw new Error('无效端口');
            this.url = `http://127.0.0.1:${info.port}`;
            clearTimeout(timer); ready = true; resolve(info);
          } catch (error) { clearTimeout(timer); reject(error); child.kill('SIGTERM'); }
        }
      });
      child.stderr.on('data', bytes => this.log('[backend] ' + bytes.toString().trim()));
      child.on('error', error => { clearTimeout(timer); reject(new Error(`无法启动 Python：${error.message}`)); });
      child.on('exit', (code, signal) => {
        clearTimeout(timer);
        this.log(`Backend exited: ${code ?? signal}`);
        this.child = null;
        this.url = null;
        if (!ready) reject(new Error(`MuJoCo 后端退出（${code ?? signal}），请检查设置中的 Python 环境及日志`));
        else if (!this.stopping) this.onUnexpectedExit?.({code, signal});
      });
    });
  }

  async command(payload) {
    if (!this.url) throw new Error('仿真后端未运行');
    const response = await fetch(`${this.url}/api/sim/command`, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: AbortSignal.timeout(1800)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);
    return result;
  }

  async stop() {
    if (this.stopPromise) return this.stopPromise;
    this.stopPromise = (async () => {
      this.stopping = true;
      const child = this.child;
      if (!child) return;
      try { await this.command({type: 'pause'}); } catch (error) { this.log('Pause on exit: ' + error.message); }
      if (child.exitCode !== null || child.signalCode !== null) return;
      await new Promise(resolve => {
        const timer = setTimeout(() => child.kill('SIGKILL'), 3000);
        child.once('exit', () => { clearTimeout(timer); resolve(); });
        child.kill('SIGTERM');
      });
    })();
    return this.stopPromise;
  }
}

module.exports = {Backend};
