// Test-only entry point. Uses a temporary profile/configuration and real Electron + MuJoCo.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {dialog, Menu} = require('electron');

module.exports = async ({window, backend, action, fileAction, configPath, root, logPath}) => {
  const locations = require('./paths.cjs').runtimePaths(root);
  const reportDir = path.join(locations.artifacts, 'reports');
  const screenshotDir = path.join(locations.artifacts, 'screenshots');
  fs.mkdirSync(reportDir, {recursive: true}); fs.mkdirSync(screenshotDir, {recursive: true});
  const checks = [];
  const js = code => window.webContents.executeJavaScript(code, true);
  const wait = async predicate => {
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      if (await predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 80));
    }
    throw new Error('Desktop check timed out');
  };
  const check = (value, message) => {assert(value, message); checks.push(message); fs.appendFileSync(logPath, 'CHECK: ' + message + '\n');};
  const state = async () => (await fetch(backend.url + '/api/sim/state')).json();
  const screenshot = async filename => {
    await js('new Promise(resolve => { setTimeout(resolve, 300); requestAnimationFrame(() => requestAnimationFrame(resolve)); })');
    await new Promise(resolve => setTimeout(resolve, 350));
    let timer;
    try {
      const image = await Promise.race([window.webContents.capturePage(), new Promise((_, reject) => {timer = setTimeout(() => reject(new Error('Screenshot timed out: ' + filename)), 10000);})]);
      fs.writeFileSync(path.join(screenshotDir, filename), image.toPNG());
    } finally { clearTimeout(timer); }
  };
  const teachingChecks=()=>require('./teaching-smoke.cjs')({js,wait,check,screenshot,configPath});
  window.setContentSize(1600, 1040);
  window.show();
  await wait(() => js('document.body.dataset.workbenchReady === "true"'));
  await wait(() => js('document.querySelector("#loading").hidden'));
  if (process.env.S1_NAVIGATION_CHECK === '1') {
    await require('./navigation-smoke.cjs')({js, wait, check, screenshot, configPath, root, fileAction, window});
    const report = {ok: true, backendPID: backend.child.pid, checks};
    fs.writeFileSync(path.join(reportDir, 'navigation-desktop-checks.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report)); window.close(); return;
  }
  if (process.env.S1_TEACHING_CHECK === '1') {
    await teachingChecks();
    const report={ok:true,backendPID:backend.child.pid,checks};
    fs.writeFileSync(path.join(reportDir,'teaching-desktop-checks.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
    window.close();
    return;
  }
  check(await js('document.querySelector("#loading").hidden && document.body.getAttribute("aria-busy") === "false"'), 'Startup surface clears only after workbench initialization');
  check((await js('typeof require')) === 'undefined', 'Renderer has no Node.js access');
  check(await js('!!window.s1Desktop && !!window.s1Studio.snapshot().backend'), 'Sandboxed preload bridge and MuJoCo connected');
  check(Menu.getApplicationMenu().items.map(item => item.label).join(',') === '文件,编辑,视图,仿真,工具,帮助', 'Native desktop menus installed');

  check(!window.isMenuBarVisible(), 'Original top native menu strip is hidden');
  check(await js(`(() => {
    const header = document.querySelector('#app-titlebar').getBoundingClientRect();
    const menu = document.querySelector('#desktop-menubar').getBoundingClientRect();
    const toolbar = document.querySelector('#workbench-toolbar').getBoundingClientRect();
    return header.bottom <= menu.top && menu.bottom <= toolbar.top && document.querySelectorAll('#desktop-menubar button').length === 6;
  })()`), 'Compact RoboStudio titlebar appears above menu strip and icon toolbar');
  check(await js(`!document.querySelector('.header') && document.querySelector('.wordmark').textContent === 'RoboStudio' && getComputedStyle(document.querySelector('#app-titlebar')).getPropertyValue('-webkit-app-region') === 'drag'`), 'Old workspace strip is removed and transparent wordmark has a draggable titlebar');
  await js('document.querySelector("[data-window-action=maximize]").click()');
  await wait(async () => window.isMaximized() && await js('document.querySelector("#app-titlebar").dataset.maximized === "true"'));
  await js('document.querySelector("[data-window-action=maximize]").click()');
  await wait(async () => !window.isMaximized() && await js('document.querySelector("#app-titlebar").dataset.maximized === "false"'));
  check(true, 'Custom maximize and restore buttons track native window state');
  window.show(); window.focus();
  await new Promise(resolve => setTimeout(resolve, 500));
  await js('document.querySelector("[data-window-action=minimize]").click()');
  await wait(async () => window.isMinimized());
  window.restore(); window.show(); window.focus();
  await wait(async () => !window.isMinimized());
  check(true, 'Custom minimize button works and window can be restored');
  check(await js(`(() => {
    const run=document.querySelector('[data-workbench="run"]');
    const pause=document.querySelector('[data-workbench="pause"]');
    return run.getBoundingClientRect().width===0 && pause.getBoundingClientRect().width>0 && document.querySelectorAll('[data-simulation-primary]').length===1;
  })()`), 'Simulation toolbar shows one start split button, with independent pause and reset');
  await action('pause');
  const startPoint=await js(`(() => {const r=document.querySelector('[data-simulation-primary] svg').getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};})()`);
  window.webContents.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...startPoint});
  // Backend polling continues while the user holds the mouse down.
  await new Promise(resolve=>setTimeout(resolve,450));
  window.webContents.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...startPoint});
  await wait(async () => (await state()).running);
  check(true,'Clicking the visible simulation arrow starts dynamics across backend refreshes');
  await action('pause');
  const fileMenu = Menu.getApplicationMenu().items[0].submenu;
  let menuShown = false;
  fileMenu.once('menu-will-show', () => {menuShown = true;});
  await js('document.querySelector("#desktop-menubar button").click(); true');
  await wait(async () => menuShown);
  fileMenu.closePopup(window);
  await wait(() => js('document.querySelector("#desktop-menubar button").getAttribute("aria-expanded") === "false"'));
  check(true, 'Relocated File menu opens the native submenu and clears its active state on dismissal');

  await action('pose');
  const originalInput = await js('document.querySelector("#pose-x").value');
  const beforeEdit = await state();
  await js('document.querySelector("#pose-x").focus(); document.querySelector("#pose-x").select()');
  await window.webContents.insertText('123');
  const clickEdit = async name => {
    const point = await js(`(() => {const r = document.querySelector('[data-workbench="${name}"]').getBoundingClientRect(); return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};})()`);
    window.webContents.sendInputEvent({type: 'mouseDown', button: 'left', clickCount: 1, ...point});
    window.webContents.sendInputEvent({type: 'mouseUp', button: 'left', clickCount: 1, ...point});
  };
  await clickEdit('undo');
  await wait(() => js(`document.querySelector('#pose-x').value === ${JSON.stringify(originalInput)}`));
  check(await js('document.activeElement.id === "pose-x"'), 'Toolbar undo restores input and preserves the edited field focus');
  await clickEdit('redo');
  await wait(() => js('document.querySelector("#pose-x").value === "123"'));
  check((await state()).command_count === beforeEdit.command_count, 'Toolbar redo restores edited text without sending robot commands');
  await clickEdit('undo');
  await wait(() => js(`document.querySelector('#pose-x').value === ${JSON.stringify(originalInput)}`));
  await action('joints');

  await action('pose');
  await screenshot('property-panel-pose.png');
  await action('joints');
  const beforePages = await state();
  await js('document.querySelector("[data-category=control]").click()');
  check(await js('!document.querySelector(".function-menu").hidden && document.querySelector("[data-category=control]").getAttribute("aria-expanded") === "true"'), 'Category arrow opens its function list');
  await js('document.querySelector(".function-menu [data-subcategory=mouse]").click()');
  await screenshot('function-category-menu.png');
  check(await js('!document.querySelector("[data-function-page=gripper]")'), 'Gripper no longer has a separate category entry');
  await js('document.querySelector("[data-function-page=joints]").click()');
  check(await js('!document.querySelector("[data-page=joints]").hidden && document.querySelector("#joint-panel").nextElementSibling.matches(".gripper-section") && document.querySelector("#gripper-slider").closest("[data-page]").dataset.page === "joints" && document.querySelector(".function-menu").hidden'), 'Joint page includes gripper controls below the joint panel');
  await js('document.querySelector("[data-category=simulation]").click(); document.querySelector("[data-function-page=simulation]").click()');
  check((await state()).command_count === beforePages.command_count, 'Selecting the simulation page does not start, pause or reset the robot');
  await js('document.querySelector("[data-category=data]").click(); document.querySelector("[data-function-page=activity]").click()');
  check(await js('!!document.querySelector(".control-panel #activity-list") && !document.querySelector("[data-page=activity]").hidden'), 'Data event log is docked on the right');
  await js('document.querySelector("[data-category=data]").click(); document.querySelector(".function-menu").dispatchEvent(new KeyboardEvent("keydown", {key:"Escape",bubbles:true}))');
  check(await js('document.querySelector(".function-menu").hidden && document.activeElement.dataset.category === "data"'), 'Escape closes category menu and restores trigger focus');
  await js('document.querySelector("#joint-tab").click()');
  const beforeTree = await state();
  await wait(() => js('document.querySelector("[data-config-page=arm-connection]").dataset.ready === "true"'));
  const armPage = async id => {
    const xr = id === 'arm-ar' || id.startsWith('xr-');
    await js(`document.querySelector('[data-category="${xr ? 'control' : 'arm-config'}"]').click(); ${xr ? "document.querySelector('.function-menu [data-subcategory=xr]').click();" : ''} document.querySelector('[data-function-page="${id}"]').click()`);
  };
  const armField = (key, value) => js(`(() => {const f=document.querySelector('[data-arm-path="${key}"]'); f.value=${JSON.stringify(value)}; f.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await armPage('arm-connection');
  check(await js(`document.querySelector('[aria-label="文件与工作区"]').contains(document.querySelector('[data-category="arm-config"]')) && document.querySelector('.arm-detection').textContent.includes('未检测')`), 'Hardware configuration opens from file toolbar and never claims a real detection');
  await armField('connection.layout','single');
  check(await js(`[...document.querySelectorAll('[data-arm-index="1"]')].every(f=>f.disabled)`), 'Single arm mode disables B fields without deleting their configuration');
  await armField('connection.layout','dual');
  await armPage('arm-devices');
  await armField('arms.1.device','can0');
  await js(`document.querySelector('[data-config-page="arm-devices"] [data-arm-action="save"]').click()`);
  await wait(()=>js(`document.querySelector('[data-config-page="arm-devices"] .arm-save-state').classList.contains('error')`));
  check(!fs.existsSync(path.join(path.dirname(configPath),'arms.json')), 'Duplicate CAN interface is rejected before writing a configuration');
  await armField('arms.1.device','can1');
  await armField('arms.0.bitrate','500000');
  await armField('arms.1.bitrate','500000');
  await js(`document.querySelector('[data-config-page="arm-devices"] [data-arm-action="save"]').click()`);
  await wait(()=>js(`document.querySelector('[data-config-page="arm-devices"] .arm-save-state').textContent.includes('配置已保存')`));
  const armSaved=JSON.parse(fs.readFileSync(path.join(path.dirname(configPath),'arms.json')));
  check(armSaved.connection.layout==='dual' && armSaved.arms[0].resetDegrees===null, 'Arm configuration persists with reset targets unset');
  await armPage('arm-startup');
  check(await js(`[...document.querySelectorAll('[data-config-page="arm-startup"] .arm-operation-grid button:not([data-hardware-action])')].every(b=>b.disabled) && [...document.querySelectorAll('[data-config-page="arm-startup"] [data-hardware-action]:not([data-hardware-action="enable"])')].every(b=>!b.disabled) && document.querySelector('[data-config-page="arm-startup"] [data-hardware-action="enable"]').disabled`), 'Explicit read and disable controls are available; enable waits for fresh feedback and confirmation; motion reset remains unavailable');
  check((await state()).command_count===beforeTree.command_count, 'Editing and saving hardware configuration sends no simulation motion commands');
  await screenshot('arm-configuration-startup.png');
  await armPage('arm-connection');
  await screenshot('arm-configuration-connection.png');
  await armPage('arm-devices');
  await screenshot('arm-configuration-devices.png');
  await armPage('xr-connection');
  check(await js(`document.querySelector('[data-category="arm-config"]').nextElementSibling === document.querySelector('[data-category="control"]') && document.querySelector('[data-category="control"]').nextElementSibling === document.querySelector('[data-category="capture"]')`), 'Data collection follows unified arm control in file toolbar');
  check(await js(`document.querySelector('#vr-transport').options.length===2 && document.querySelector('[data-page="xr-connection"]').textContent.includes('RoboData')`), 'RoboData connection page offers USB and Wi-Fi');
  await js(`document.querySelector('#vr-transport').value='wifi';document.querySelector('#vr-transport').dispatchEvent(new Event('change'));`);
  check(await js(`!document.querySelector('#vr-network').hidden`), 'Wi-Fi selection reveals host and pairing information without applying it');
  await screenshot('xr-connection.png');
  await js(`document.querySelector('[data-category="capture"]').click();document.querySelector('[data-function-page="capture-session"]').click()`);
  check(await js(`!document.querySelector('[data-page="capture-session"]').hidden && document.querySelector('#capture-task').maxLength===80`), 'Collection page shows task naming and recording controls');
  await screenshot('robodata-recording.png');
  await armPage('xr-guide');
  check(await js(`document.querySelector('[data-page="xr-guide"]').hidden===false`), 'AR/VR usage guide opens independently');
  await screenshot('xr-guide.png');
  await action('joints');
  const node = id => `document.querySelector('[data-node="${id}"]')`;
  await js(`${node('joints')}.querySelector('.project-toggle').click()`);
  check(await js(`${node('joints')}.getAttribute('aria-expanded') === 'true' && ${node('joints')}.querySelectorAll('[role="treeitem"]').length === 6`), 'Joint group expands into six real joint objects');
  await js(`${node('joint-3')}.querySelector('.project-row').click()`);
  check(await js('document.querySelector("#joint-tab").getAttribute("aria-selected") === "true" && document.querySelector("#joint-value-3").closest(".joint-control").classList.contains("tree-highlight")'), 'Selecting a joint opens its existing control and highlights its angle row');
  await js(`${node('robot')}.querySelector('.project-toggle').click()`);
  check(await js(`${node('robot')}.getAttribute('aria-expanded') === 'false' && ${node('robot')}.getAttribute('aria-selected') === 'true' && document.querySelectorAll('#project-tree [tabindex="0"]').length === 1`), 'Collapsing a parent hides children and keeps a visible selected tree item');
  await js(`${node('robot')}.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))`);
  check(await js(`${node('robot')}.getAttribute('aria-expanded') === 'true'`), 'Arrow keys expand the selected tree branch');
  await js(`${node('target')}.querySelector('.project-row').click()`);
  check(await js('document.querySelector("#pose-tab").getAttribute("aria-selected") === "true"'), 'Current target node opens the existing end-effector pose editor');
  await js(`${node('tcp')}.querySelector('.project-row').click()`);
  check(await js('document.querySelector(".pose-help").open'), 'TCP object opens model reference-point details');
  await js(`${node('gripper')}.querySelector('.project-row').click()`);
  check(await js('!document.querySelector("[data-page=joints]").hidden'), 'Gripper tree shortcut opens the combined joint page');
  check((await state()).command_count === beforeTree.command_count, 'Navigating and expanding objects sends no robot motion commands');
  check(await js('document.querySelectorAll("#workbench-toolbar [data-view]").length === 4 && document.querySelector("#workbench-toolbar #grid-toggle") && [...document.querySelectorAll("#workbench-toolbar button")].every(b => b.getAttribute("aria-label") && b.title)'), 'Existing view controls are consolidated into labeled icon toolbar groups');
  await js('document.querySelector("[data-view=top]").click(); document.querySelector("#grid-toggle").click()');
  check(await js('document.querySelector("[data-view=top]").classList.contains("active") && document.querySelector("#grid-toggle").getAttribute("aria-pressed") === "true"'), 'Moved view and grid buttons retain their working handlers');
  await js('document.querySelector("[data-view=iso]").click(); document.querySelector("#grid-toggle").click()');
  await js(`${node('joints')}.querySelector('.project-toggle').click(); ${node('robot')}.querySelector('.project-row').click()`);
  await screenshot('project-tree-toolbar.png');
  window.setContentSize(1440, 900);
  await screenshot('project-tree-toolbar-1440.png');
  await js('document.querySelector("[data-workbench=translate]").click()');
  check(await js('document.querySelector("#drag-toggle").getAttribute("aria-pressed") === "true" && document.querySelector("[data-workbench=translate]").getAttribute("aria-pressed") === "true"'), 'Translation icon enables the existing target handle and shows active mode');
  await js('document.querySelector("[data-workbench=translate]").click()');
  check(await js('document.querySelector("#drag-toggle").getAttribute("aria-pressed") === "false"'), 'Clicking the active handle icon disables dragging through the existing control');

  // Startup is now all-zero; use a reachable fixture for the existing IK check.
  await backend.command({type: 'settings', mode: 'kinematic'});
  const fixture = await backend.command({type: 'joints', joints: [0,1.05,1.55,.5,0,0], gripper: 40});
  await wait(() => js(`window.s1Studio.snapshot().backend.sequence >= ${fixture.sequence}`));
  await action('pose');
  await js('document.querySelector("#pose-sync").click()');
  const initial = await state();
  await js(`document.querySelector('#pose-z').value = ${initial.tcp.position[2]*1000+10}; document.querySelector('#pose-apply').click();`);
  await wait(async () => Math.abs((await state()).tcp.position[2] - initial.tcp.position[2] - .01) < .0005);
  check(true, 'Cartesian IK works inside desktop window');
  await action('rotate');
  check(await js('document.querySelector("#drag-mode").value === "rotate" && document.querySelector("#drag-toggle").getAttribute("aria-pressed") === "true"'), 'Native action enables end-effector rotation handle');
  await action('translate');

  await action('settings');
  check(await js('document.querySelector("#settings-dialog").open'), 'Settings dialog opens through desktop IPC');
  await js(`document.querySelector('#setting-speed').value = '.42'; document.querySelector('#setting-position').value = '.3'; document.querySelector('#setting-obstacle').checked = true;`);
  await screenshot('desktop-settings.png');
  await js('document.querySelector("#settings-save").click()');
  await wait(() => js('!document.querySelector("#settings-dialog").open'));
  check(JSON.parse(fs.readFileSync(configPath)).simulation.speed_rad_s === .42 && (await state()).speed_rad_s === .42, 'Settings persist externally and apply to the running backend');

  const workspace = path.join(path.dirname(configPath), 'test-workspace.s1studio');
  const realSave = dialog.showSaveDialog, realOpen = dialog.showOpenDialog;
  dialog.showSaveDialog = async () => ({canceled: false, filePath: workspace});
  dialog.showOpenDialog = async () => ({canceled: false, filePaths: [workspace]});
  try {
    await fileAction('save');
    const saved = JSON.parse(fs.readFileSync(workspace));
    check(saved.format === 's1-studio-workspace' && !((await state()).running), 'Workspace save records pose/view and pauses simulation');
    const target = [...saved.joints]; target[0] += .015;
    await backend.command({type: 'joints', joints: target, gripper: 65});
    await fileAction('open');
    const restored = await state();
    await wait(() => js('document.querySelector("#tree-label-workspace").textContent === "test-workspace.s1studio"'));
    check(restored.joints.every((q, i) => Math.abs(q-saved.joints[i]) < 1e-7) && Math.abs(restored.gripper-saved.gripper) < 1e-5 && window.getTitle().includes('test-workspace'), 'Opening a workspace restores robot state and updates window title');
  } finally {dialog.showSaveDialog = realSave; dialog.showOpenDialog = realOpen;}

  Menu.getApplicationMenu().items.find(item => item.label === '仿真').submenu.items[0].click();
  await wait(async () => (await state()).running);
  await wait(async () => (await state()).simulation_time > .15);
  await action('pause');
  check(!(await state()).running, 'Native run/pause actions control real MuJoCo dynamics');
  await action('translate');
  await action('activity');
  await screenshot('desktop-stage3.png');
  await teachingChecks();
  // Leave dynamics running, then exercise the actual window-close handler.
  await action('run');
  const report = {ok: true, backendPID: backend.child.pid, backendURL: backend.url,
    electron: process.versions.electron, chrome: process.versions.chrome, logPath, checks};
  fs.writeFileSync(path.join(reportDir, 'desktop-checks.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await js('setTimeout(() => document.querySelector("[data-window-action=close]").click(), 50); true');
};
