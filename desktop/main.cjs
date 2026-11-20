const {app, BrowserWindow, Menu, ipcMain, dialog, shell, session, nativeTheme} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {Backend} = require('./backend.cjs');
const {defaults, readSettings, validateSettings, atomicJSON, validateWorkspace, validateProjectShortcuts} = require('./config.cjs');
const {readArmConfig, saveArmConfig} = require('./arm-config.cjs');

const root = path.resolve(__dirname, '..');
const smoke = process.argv.includes('--s1-smoke-test');
const {runtimePaths} = require('./paths.cjs');
// Test-only profile and settings must never overwrite daily user state.
if (smoke) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 's1-desktop-check-'));
  Object.assign(process.env, {S1_STUDIO_DATA_DIR: temp, S1_STUDIO_CONFIG_DIR: path.join(temp, 'config'),
    S1_STUDIO_LOG_DIR: path.join(temp, 'logs'), S1_STUDIO_WORKSPACES_DIR: path.join(temp, 'workspaces')});
}
const locations = runtimePaths(root);
const configPath = path.join(locations.config, 'settings.json');
const windowPath = path.join(locations.config, 'window-state.json');
const logDir = locations.logs;
fs.mkdirSync(logDir, {recursive: true});
const logPath = path.join(logDir, 'desktop.log');
if (fs.existsSync(logPath) && fs.statSync(logPath).size > 1024*1024) fs.renameSync(logPath, logPath + '.previous');
const log = message => fs.appendFileSync(logPath, new Date().toISOString() + ' ' + message + '\n');
app.setName('S1 Studio');
app.setPath('userData', locations.profile);
app.setDesktopName('s1-studio.desktop');
// This workbench renders WebGL, but does not use hardware video codecs.
// Electron 45 VAAPI requires a newer ABI than Ubuntu's installed libva.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('disable-accelerated-video-decode');
  app.commandLine.appendSwitch('disable-accelerated-video-encode');
}

if (smoke) {
  app.commandLine.appendSwitch('use-angle', 'swiftshader');
  if (process.env.DISPLAY) app.commandLine.appendSwitch('ozone-platform', 'x11');
}
let window, backend, quitting = false, workspacePath = null, settings;
const pendingActions = new Map();
let actionId = 0;

function trusted(event) {
  if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) throw new Error('不允许的工作台请求');
}

function action(name, value) {
  if (!window || window.isDestroyed()) return Promise.reject(new Error('工作台未就绪'));
  return new Promise((resolve, reject) => {
    const id = ++actionId;
    const timer = setTimeout(() => {pendingActions.delete(id); reject(new Error('工作台未响应，请等待模型加载完成'));}, 10000);
    pendingActions.set(id, {resolve, reject, timer});
    window.webContents.send('s1:action', {id, name, value});
  });
}

function title() {
  const name = workspacePath ? path.basename(workspacePath) : 'RoboDK';
  window?.setTitle(`${name} — RoboStudio`);
  if (backend && window && !window.isDestroyed()) window.webContents.send('s1:action', {name: 'workspace-title', value: {name, path: workspacePath}});
}

async function report(task) {
  try { return await task(); }
  catch (error) { log(error.stack || error.message); if (!quitting) await dialog.showMessageBox(window, {type: 'error', title: 'S1 Studio', message: error.message, detail: '详细记录已保存到 artifacts/logs/desktop.log。'}); }
}

async function fileAction(name) {
  if (name === 'new') {
    const answer = await dialog.showMessageBox(window, {type: 'question', message: '新建工作区？', detail: '当前仿真将暂停并重置。需要保留的姿态请先保存工作区。', buttons: ['取消', '新建'], defaultId: 0, cancelId: 0});
    if (answer.response !== 1) return;
    await action('new'); workspacePath = null; title();
  } else if (name === 'open') {
    const answer = await dialog.showOpenDialog(window, {title: '打开 S1 工作区', defaultPath: locations.workspaces, properties: ['openFile'], filters: [{name: 'S1 Studio 工作区', extensions: ['s1studio', 'json']}]});
    if (answer.canceled) return;
    const filename = answer.filePaths[0];
    if (fs.statSync(filename).size > 65536) throw new Error('工作区文件过大');
    const document = validateWorkspace(JSON.parse(fs.readFileSync(filename, 'utf8')));
    await action('workspace-load', document); workspacePath = filename; title();
  } else if (name === 'save' || name === 'save-as') {
    const document = validateWorkspace(await action('workspace-snapshot'));
    let filename = name === 'save' ? workspacePath : null;
    if (!filename) {
      fs.mkdirSync(locations.workspaces, {recursive: true});
      const answer = await dialog.showSaveDialog(window, {title: '保存 S1 工作区', defaultPath: workspacePath || path.join(locations.workspaces, 'RoboDK.s1studio'), filters: [{name: 'S1 Studio 工作区', extensions: ['s1studio']}]});
      if (answer.canceled) return;
      filename = answer.filePath;
    }
    atomicJSON(filename, document); workspacePath = filename; title();
    await action('notice', '工作区已保存：' + path.basename(filename));
  } else if (name === 'settings') return action('settings');
  else if (name === 'logs') return shell.openPath(logDir);
  else throw new Error('未知文件操作');
}

function installMenu() {
  const send = name => () => report(() => action(name));
  const file = name => () => report(() => fileAction(name));
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label: '文件', submenu: [
      {label: '新建工作区', accelerator: 'CmdOrCtrl+N', click: file('new')},
      {label: '打开工作区…', accelerator: 'CmdOrCtrl+O', click: file('open')},
      {label: '保存工作区', accelerator: 'CmdOrCtrl+S', click: file('save')},
      {label: '工作区另存为…', accelerator: 'CmdOrCtrl+Shift+S', click: file('save-as')},
      {type: 'separator'}, {label: '退出', accelerator: 'Alt+F4', click: () => app.quit()},
    ]},
    {label: '编辑', submenu: [{role: 'undo', label: '撤销输入'}, {role: 'redo', label: '重做输入'}, {type: 'separator'}, {role: 'cut', label: '剪切'}, {role: 'copy', label: '复制'}, {role: 'paste', label: '粘贴'}, {role: 'selectAll', label: '全选'}]},
    {label: '视图', submenu: [
      ...[['透视', 'view-iso', 'Alt+1'], ['正视', 'view-front', 'Alt+2'], ['侧视', 'view-side', 'Alt+3'], ['俯视', 'view-top', 'Alt+4'], ['适应模型', 'fit', 'F8']].map(([label, name, accelerator]) => ({label, accelerator, click: send(name)})),
      {type: 'separator'}, {label: '场景面板', click: send('scene-panel')}, {label: '控制面板', click: send('control-panel')}, {label: '事件记录', click: send('activity')}, {type: 'separator'}, {role: 'togglefullscreen', label: '全屏', accelerator: 'F11'},
    ]},
    {label: '仿真', submenu: [
      {label: '开始动力学仿真', accelerator: 'F5', click: send('run')}, {label: '暂停', accelerator: 'F6', click: send('pause')}, {label: '重置仿真', click: send('reset')},
      {type: 'separator'}, {label: '关节控制', click: send('joints')}, {label: '末端位姿', click: send('pose')}, {label: '末端平移手柄', click: send('translate')}, {label: '末端旋转手柄', click: send('rotate')},
    ]},
    {label: '工具', submenu: [
      {label: '设置…', accelerator: 'CmdOrCtrl+,', click: file('settings')}, {label: '打开日志文件夹', click: file('logs')},
      {type: 'separator'}, {label: '重新加载界面', accelerator: 'CmdOrCtrl+Shift+R', click: () => report(async () => {await backend.command({type: 'pause'}); window.reload();})},
      {label: '开发者工具', accelerator: 'F12', click: () => window.webContents.toggleDevTools()},
    ]},
    {label: '帮助', submenu: [
      {label: '使用说明', click: () => report(() => action('help'))},
      {label: '关于 S1 Studio', click: () => dialog.showMessageBox(window, {type: 'info', title: '关于 S1 Studio', message: 'S1 Studio 0.3.0', detail: `S1 V1 机器人工作台\n末端控制 · 碰撞检查 · MuJoCo 仿真\n\nElectron ${process.versions.electron} / Chromium ${process.versions.chrome}\n项目目录：${root}\n当前 TCP 为未标定模型参考点。`})},
    ]},
  ]));
}

async function closeApplication() {
  if (quitting) return;
  quitting = true;
  try {
    if (window && !window.isDestroyed()) {
      atomicJSON(windowPath, {bounds: window.getNormalBounds(), maximized: window.isMaximized()});
      window.webContents.send('s1:action', {name: 'closing'});
    }
    await backend?.stop();
  } catch (error) { log('Exit: ' + error.stack); }
  finally {
    for (const pending of pendingActions.values()) {clearTimeout(pending.timer); pending.reject(new Error('软件正在退出'));}
    pendingActions.clear();
    app.exit(0);
  }
}

if (!smoke && !app.requestSingleInstanceLock()) app.exit(0);
else {
  app.on('second-instance', () => {if (window?.isMinimized()) window.restore(); window?.show(); window?.focus();});
  app.on('before-quit', event => {event.preventDefault(); closeApplication();});
  app.on('window-all-closed', () => app.quit());
  process.on('SIGTERM', () => app.quit());
  process.on('SIGINT', () => app.quit());
  process.on('exit', () => backend?.child?.kill('SIGTERM'));
  app.whenReady().then(async () => {
    nativeTheme.themeSource = 'dark';
    settings = readSettings(configPath);
    let saved = {};
    try { saved = JSON.parse(fs.readFileSync(windowPath, 'utf8')); } catch {}
    const bounds = saved.bounds || {};
    window = new BrowserWindow({width: Math.max(1100, bounds.width || 1480), height: Math.max(760, bounds.height || 960),
      minWidth: 1050, minHeight: 720, backgroundColor: '#f7f7f7', title: 'RoboStudio', frame: false, show: !smoke,
      icon: path.join(__dirname, 'robostudio-rs.png'), autoHideMenuBar: false,
      webPreferences: {preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true, backgroundThrottling: false},
    });
    if (saved.maximized && !smoke) window.maximize();
    window.on('close', event => {event.preventDefault(); closeApplication();});
    const windowState = () => ({maximized: window.isMaximized()});
    for (const event of ['maximize', 'unmaximize']) {
      window.on(event, () => window.webContents.send('s1:window-state', windowState()));
    }
    ipcMain.handle('s1:window-state', event => {trusted(event); return windowState();});
    ipcMain.handle('s1:window-action', (event, name) => {
      trusted(event);
      if (name === 'minimize') window.minimize();
      else if (name === 'maximize') {if (window.isMaximized()) window.unmaximize(); else window.maximize();}
      else if (name === 'close') window.close();
      else throw new Error('未知窗口操作');
    });
    window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
    window.webContents.on('will-navigate', (event, url) => {if (!backend?.url || new URL(url).origin !== backend.url) event.preventDefault();});
    window.webContents.on('will-redirect', event => event.preventDefault());
    window.webContents.on('render-process-gone', (_event, details) => {log('Renderer exited: ' + details.reason); backend?.command({type: 'pause'}).catch(error => log(error.message));});
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
    session.defaultSession.on('will-download', event => event.preventDefault());
    installMenu();
    // Keep native menu actions/accelerators, place their triggers below the workspace header.
    window.setMenuBarVisibility(false);
    ipcMain.handle('s1:menus', event => {
      trusted(event); return Menu.getApplicationMenu().items.map(item => item.label);
    });
    ipcMain.handle('s1:menu-popup', (event, index, position) => {
      trusted(event);
      const menu = Number.isInteger(index) && Menu.getApplicationMenu().items[index]?.submenu;
      if (!menu || !Number.isFinite(position?.x) || !Number.isFinite(position?.y)) throw new Error('菜单位置无效');
      const [width, height] = window.getContentSize();
      const zoom = window.webContents.getZoomFactor();
      return new Promise(resolve => menu.popup({window,
        x: Math.round(Math.max(0, Math.min(width - 1, position.x * zoom))),
        y: Math.round(Math.max(0, Math.min(height - 1, position.y * zoom))),
        callback: () => resolve(true),
      }));
    });
    ipcMain.on('s1:action-result', (event, message) => {
      trusted(event);
      const pending = pendingActions.get(message.id);
      if (!pending) return;
      clearTimeout(pending.timer); pendingActions.delete(message.id);
      if (message.result?.ok) pending.resolve(message.result.value);
      else pending.reject(new Error(message.result?.message || '操作失败'));
    });
    ipcMain.handle('s1:edit-action', (event, name) => {
      trusted(event);
      if (name === 'undo') window.webContents.undo();
      else if (name === 'redo') window.webContents.redo();
      else throw new Error('未知编辑操作');
    });
    ipcMain.handle('s1:info', event => {trusted(event); return {version: '0.3.0', workspaceName: workspacePath ? path.basename(workspacePath) : 'RoboDK', workspacePath, root, configPath, logPath, python: backend?.python, engine: 'Electron ' + process.versions.electron};});
    ipcMain.handle('s1:settings-read', event => {trusted(event); return readSettings(configPath);});
    const shortcutsPath = path.join(locations.config, 'project-shortcuts.json');
    ipcMain.handle('s1:project-shortcuts-read', event => {
      trusted(event);
      return fs.existsSync(shortcutsPath) ? validateProjectShortcuts(JSON.parse(fs.readFileSync(shortcutsPath, 'utf8'))) : [];
    });
    ipcMain.handle('s1:project-shortcuts-save', (event, value) => {
      trusted(event); const next = validateProjectShortcuts(value); atomicJSON(shortcutsPath, next); return next;
    });
    const armConfigPath = path.join(locations.config, 'arms.json');
    ipcMain.handle('s1:arm-config-read', event => {trusted(event); return readArmConfig(armConfigPath);});
    ipcMain.handle('s1:arm-config-save', (event, config) => {trusted(event); return saveArmConfig(armConfigPath, config);});
    ipcMain.handle('s1:settings-save', async (event, input) => {
      trusted(event);
      const next = validateSettings(input);
      if (next.pythonPath !== settings.pythonPath) throw new Error('此设置窗口保留当前 Python 环境；如需更换请编辑 .local/config/settings.json 后重启软件');
      const previous = settings;
      await action('configure', next.simulation);
      try {atomicJSON(configPath, next); settings = next;}
      catch (error) {await action('configure', previous.simulation); throw error;}
      return next;
    });
    ipcMain.handle('s1:file-action', async (event, name) => {trusted(event); return report(() => fileAction(name));});
    await window.loadFile(path.join(__dirname, 'loading.html'));
    backend = new Backend({root, configPath, log, onUnexpectedExit: () => {
      if (!quitting) {action('backend-exited').catch(error => log(error.message)); dialog.showMessageBox(window, {type: 'error', message: '仿真后端已退出', detail: '控制已停用。请查看日志并重新启动 S1 Studio。'});}
    }});
    await backend.start(settings);
    await window.loadURL(backend.url);
    title();
    if (smoke) await require('./smoke.cjs')({app, window, backend, action, fileAction, configPath, root, logPath});
  }).catch(async error => {
    log(error.stack || error.message);
    if (smoke) {console.error(error); await backend?.stop(); app.exit(1);}
    else {dialog.showErrorBox('S1 Studio 启动失败', `${error.message}\n\n请检查 .local/config/settings.json 和 artifacts/logs/desktop.log。`); closeApplication();}
  });
}
