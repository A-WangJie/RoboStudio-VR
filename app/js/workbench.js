import { installFunctionPages } from './function-pages.js';
import { toolbarIcon } from './toolbar-icons.js';
import { installProjectTree } from './project-tree.js';
import { installWorkspaceLayout } from './workspace-layout.js';
import { loadShortcutPreferences } from './project-shortcuts.js';

const $ = selector => document.querySelector(selector);

export async function installWorkbench({state, viewport, session}) {
  await loadShortcutPreferences();
  installWorkspaceLayout();
  const desktop = window.s1Desktop;
  document.body.classList.toggle('desktop', !!desktop);
  if (desktop?.menus && desktop?.popupMenu) {
    const bar = $('#desktop-menubar');
    const labels = await desktop.menus();
    labels.forEach((label, index) => {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
      button.setAttribute('aria-haspopup', 'menu'); button.setAttribute('aria-expanded', 'false');
      button.addEventListener('click', async () => {
        const bounds = button.getBoundingClientRect(); button.setAttribute('aria-expanded', 'true');
        try { await desktop.popupMenu(index, {x: bounds.left, y: bounds.bottom}); }
        catch (error) { console.error('打开菜单失败', error); }
        finally { button.setAttribute('aria-expanded', 'false'); }
      });
      button.addEventListener('keydown', event => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
          event.preventDefault(); bar.children[(index + (event.key === 'ArrowRight' ? 1 : -1) + labels.length) % labels.length].focus();
        } else if (event.key === 'ArrowDown') {event.preventDefault(); button.click();}
      });
      bar.append(button);
    });
    bar.hidden = false;
  }
  const toolbar = $('#workbench-toolbar');
  const groups = [
    ['文件与工作区', [['new', '新建工作区', 'new-workspace', true], ['open', '打开工作区', 'open', true], ['save', '保存工作区', 'save', true]]],
    ['撤销与重做', [['undo', '撤销输入', 'undo', true], ['redo', '重做输入', 'redo', true]]],
    ['视图与显示', [['fit', '适应模型', 'fit'],
      ['iso', '透视', null, false, '[data-view="iso"]'], ['front', '正视', null, false, '[data-view="front"]'],
      ['side', '侧视', null, false, '[data-view="side"]'], ['top', '俯视', null, false, '[data-view="top"]'],
      ['grid', '显示 / 隐藏网格', null, false, '#grid-toggle'], ['axes', '显示 / 隐藏坐标轴', null, false, '#axes-toggle']]],
    ['机械臂与末端控制', [['robot', '关节控制', 'joints'], ['target', '末端位姿', 'pose'], ['gripper', '夹爪开合', 'gripper'],
      ['move', '末端平移手柄', 'translate'], ['rotate', '末端旋转手柄', 'rotate'], ['home', '恢复关节初始姿态', 'home']]],
    ['动力学仿真', [['play', '开始动力学仿真', 'run'], ['pause', '暂停仿真', 'pause'], ['reset', '重置仿真', 'reset']]],
    ['工具与帮助', [['settings', '设置', 'settings', true], ['list', '事件记录', 'activity'], ['help', '使用说明', 'help']]],
  ];
  for (const [label, group] of groups) {
    const element = document.createElement('div');
    element.className = 'tool-group' + (group.every(item => item[3]) ? ' desktop-only' : '');
    element.setAttribute('role', 'group'); element.setAttribute('aria-label', label);
    for (const [symbol, label, action, desktopOnly, selector] of group) {
      // Move existing view buttons so their tested handlers and state stay authoritative.
      const button = selector ? document.querySelector(selector) : document.createElement('button');
      button.type = 'button';
      if (action) button.dataset.workbench = action;
      button.classList.add('tool-button', 'icon-' + symbol);
      if (desktopOnly) button.classList.add('desktop-only');
      button.title = label + ({'new-workspace': '（Ctrl+N）', save: '（Ctrl+S，暂停并保存当前位姿）', open: '（Ctrl+O）', fit: '（F8）', run: '（F5）', pause: '（F6）', settings: '（Ctrl+,）'}[action] || '');
      button.setAttribute('aria-label', label);
      button.innerHTML = toolbarIcon(symbol);
      if (action) button.addEventListener('click', () => invoke(action));
      // Keep the edited field focused so native undo/redo targets its input history.
      if (action === 'undo' || action === 'redo') {
        button.title = `${label}（${action === 'undo' ? 'Ctrl+Z' : 'Ctrl+Shift+Z'}）`;
        button.addEventListener('mousedown', event => event.preventDefault());
      }
      element.append(button);
    }
    toolbar.append(element);
  }
  // All existing view operations are now together in the top icon toolbar.
  document.querySelector('.viewport-toolbar').hidden = true;
  const projectTree = installProjectTree({invoke});
  function syncToolState() {
    const dragging = session.ready && $('#drag-toggle').getAttribute('aria-pressed') === 'true';
    for (const name of ['translate', 'rotate']) {
      const active = dragging && $('#drag-mode').value === name;
      const button = toolbar.querySelector(`[data-workbench="${name}"]`);
      button.setAttribute('aria-pressed', String(active));
      button.title = active ? `关闭末端${name === 'translate' ? '平移' : '旋转'}手柄` : `开启末端${name === 'translate' ? '平移' : '旋转'}手柄`;
    }
    toolbar.querySelector('[data-workbench="joints"]').setAttribute('aria-pressed', $('#joint-tab').getAttribute('aria-selected'));
    toolbar.querySelector('[data-workbench="pose"]').setAttribute('aria-pressed', $('#pose-tab').getAttribute('aria-selected'));
  }
  for (const id of ['drag-toggle', 'joint-tab', 'pose-tab']) new MutationObserver(syncToolState).observe($('#' + id), {attributes: true, attributeFilter: ['aria-pressed', 'aria-selected']});
  $('#drag-mode').addEventListener('change', syncToolState);
  syncToolState();
  const tag = document.createElement('span'); tag.id = 'workbench-engine'; tag.className = 'workbench-engine';
  toolbar.append(tag);

  const activity = document.createElement('section'); activity.className = 'activity-panel'; activity.hidden = true;
  activity.innerHTML = '<div class="activity-heading"><span>事件记录</span><small>当前会话</small><button id="clear-activity">清空</button><button id="close-activity" aria-label="关闭事件记录">×</button></div><ol id="activity-list" aria-live="polite"></ol>';
  $('.viewport-panel').append(activity);
  $('#clear-activity').addEventListener('click', () => $('#activity-list').replaceChildren());
  $('#close-activity').addEventListener('click', () => {activity.hidden = true;});

  const settingsDialog = document.createElement('dialog'); settingsDialog.id = 'settings-dialog';
  settingsDialog.innerHTML = `<form id="settings-form"><div class="dialog-heading"><div><small>APPLICATION SETTINGS</small><h2>工作台设置</h2></div><button type="button" data-dialog-close aria-label="关闭设置">×</button></div>
    <p class="dialog-note">修改后保存即可应用；仿真会先暂停。设置会保留到下次启动。</p>
    <label class="setting-field"><span>关节目标变化速度<small>动力学参考斜坡，非真机速度限制</small></span><span><input id="setting-speed" type="number" min="0.01" max="2" step="0.01" required> rad/s</span></label>
    <label class="setting-field"><span>逆解位置容差</span><span><input id="setting-position" type="number" min="0.01" max="5" step="0.01" required> mm</span></label>
    <label class="setting-field"><span>逆解姿态容差</span><span><input id="setting-orientation" type="number" min="0.01" max="10" step="0.01" required> deg</span></label>
    <label class="check-row"><input id="setting-collision" type="checkbox">启用碰撞拦截，并设为启动默认值</label>
    <label class="check-row"><input id="setting-obstacle" type="checkbox">显示测试障碍物，并设为启动默认值</label>
    <div class="settings-location"><span>配置文件</span><code id="setting-path"></code><span>后端 Python</span><code id="setting-python"></code><small>Python 环境可在外部配置的 pythonPath 中修改，重启软件后使用。</small></div>
    <p id="settings-result" role="status"></p><div class="dialog-actions"><button type="button" data-dialog-close>取消</button><button id="settings-save" type="submit" class="primary-button">保存并应用</button></div></form>`;
  document.body.append(settingsDialog);
  settingsDialog.querySelectorAll('[data-dialog-close]').forEach(button => button.addEventListener('click', () => settingsDialog.close()));

  const help = document.createElement('dialog'); help.className = 'help-dialog';
  help.innerHTML = `<div class="dialog-heading"><div><small>S1 STUDIO</small><h2>工作台使用说明</h2></div><button aria-label="关闭使用说明">×</button></div><p>三维视图：按住鼠标左键拖动旋转视角，滚动滚轮缩放，按住右键拖动平移。顶部工具栏可切换透视、正视、侧视和俯视，或适应模型。</p><p>坐标以机械臂基座为参考，X / Y / Z 分别对应三个坐标轴；底部坐标栏显示末端参考点的位置，单位为 mm。</p><p>右侧切换关节控制 / 末端位姿。末端目标使用基座坐标，位置 mm、姿态 deg。</p><p>工具栏可开启末端平移 / 旋转手柄；机械臂显示实际仿真姿态，手柄表示请求目标。</p><p>F5 开始动力学，F6 暂停，F8 适应视图。默认运动学模式便于先核对位姿。</p><p>工作区文件保存当前实际关节、夹爪、视角和障碍物开关。保存时先暂停；打开时使用运动学模式并重新检查碰撞。</p><p>设置窗口可调整目标速度和逆解容差。关闭桌面软件会结束其专属仿真后端。</p><p class="dialog-note">当前为仿真工作台；VR 设备及真机尚未连接。模型 TCP 未标定，凸包与离散碰撞检查用于仿真验证。</p>`;
  document.body.append(help); help.querySelector('button').addEventListener('click', () => help.close());

  const functionPages = installFunctionPages({toolbar, activity, settingsDialog, help, invoke});

  let settings;
  function notice(text, error = false) {
    const list = $('#activity-list');
    if (list.lastElementChild?.dataset.message === text) return;
    const item = document.createElement('li'); item.dataset.message = text; item.classList.toggle('event-error', error);
    const time = document.createElement('time'); time.textContent = new Date().toLocaleTimeString('zh-CN', {hour12: false});
    const content = document.createElement('span'); content.textContent = text;
    item.append(time, content); list.append(item);
    while (list.children.length > 80) list.firstElementChild.remove();
    list.scrollTop = list.scrollHeight;
  }
  window.addEventListener('s1:notice', event => notice(event.detail.text, event.detail.error));
  function update(snapshot) {
    tag.textContent = snapshot ? `${snapshot.engine} · ${snapshot.running ? '动力学运行中' : snapshot.mode === 'dynamic' ? '动力学已暂停' : '运动学验证'}` : '本地模型预览';
    toolbar.querySelector('[data-workbench="pause"]').disabled = !snapshot?.running;
    for (const name of ['run', 'reset', 'translate', 'rotate']) toolbar.querySelector(`[data-workbench="${name}"]`).disabled = !session.ready || ((name === 'translate' || name === 'rotate') && viewport.software);
    toolbar.querySelector('[data-workbench="run"]').disabled = !session.ready || !!snapshot?.running;
    toolbar.querySelector('[data-workbench="home"]').disabled = $('#home-pose').disabled;
    syncToolState();
  }
  window.addEventListener('s1:backend-state', event => update(event.detail));
  window.addEventListener('s1:backend-disconnected', () => {update(null); tag.textContent = '后端连接中断';});
  update(session.snapshot);

  async function command(payload) {
    const result = await session.send(payload);
    if (!result?.ok) throw new Error(result?.message || '后端控制未就绪');
    return result.state;
  }

  async function execute(name, value) {
    if (name === 'undo' || name === 'redo') return desktop?.editAction(name);
    if (name === 'new-workspace') return desktop?.fileAction('new');
    if (name === 'workspace-title') {
      const file = typeof value === 'string' ? {name: value} : value;
      projectTree.setWorkspaceName(file.name, file.path);
      document.title = `${file.name} — RoboStudio`; return;
    }
    if (name === 'function-page') {functionPages.open(value.id, value.keys); return;}
    if (['open', 'save', 'save-as'].includes(name)) return desktop?.fileAction(name);
    if (name.startsWith('view-')) {document.querySelector(`[data-view="${name.slice(5)}"]`)?.click(); return;}
    if (name === 'fit') return viewport.fit();
    if (name === 'joints' || name === 'pose') {
      document.body.classList.remove('hide-control-panel');
      $(name === 'joints' ? '#joint-tab' : '#pose-tab').click();
      $('.control-content').scrollTop = 0; return;
    }
    if (name === 'gripper') {
      document.body.classList.remove('hide-control-panel');
      functionPages.show('joints');
      $('.gripper-section').scrollIntoView({block: 'nearest'}); return;
    }
    if (name === 'tcp') {
      await execute('pose'); $('.pose-help').open = true;
      $('.pose-help').scrollIntoView({block: 'nearest'}); return;
    }
    if (name === 'home') {$('#home-pose').click(); return;}
    if (name === 'scene-panel' || name === 'control-panel') {document.body.classList.toggle('hide-' + name); return;}
    if (name === 'activity') {functionPages.show('activity'); return;}
    if (name === 'help') {functionPages.show('help'); if (!help.open) help.show(); return;}
    if (name === 'notice') {notice(value); return;}
    if (name === 'closing') {
      const curtain = document.createElement('div'); curtain.className = 'exit-curtain'; curtain.textContent = '正在暂停仿真并关闭工作台…'; document.body.append(curtain); return;
    }
    if (name === 'backend-exited') {session.disconnect(); update(null); notice('仿真后端已退出，请检查日志并重启软件。', true); return;}
    if (name === 'settings') {
      if (!desktop) return;
      settings = await desktop.settings();
      const info = await desktop.info();
      $('#setting-speed').value = settings.simulation.speed_rad_s;
      $('#setting-position').value = settings.simulation.ik_position_tolerance_mm;
      $('#setting-orientation').value = settings.simulation.ik_orientation_tolerance_deg;
      $('#setting-collision').checked = settings.simulation.collision_protection;
      $('#setting-obstacle').checked = settings.simulation.obstacle;
      $('#setting-path').textContent = info.configPath;
      $('#setting-python').textContent = info.python;
      $('#settings-result').textContent = '';
      functionPages.show('settings'); if (!settingsDialog.open) settingsDialog.show(); return;
    }
    if (!session.ready) throw new Error('MuJoCo 后端尚未连接');
    if (name === 'run') {
      if (session.snapshot.mode !== 'dynamic') await command({type: 'settings', mode: 'dynamic'});
      await command({type: 'resume'}); notice('动力学仿真已开始'); return;
    }
    if (name === 'pause' || name === 'reset') {await command({type: name}); session.syncTarget(); notice(name === 'pause' ? '仿真已暂停' : '仿真已重置'); return;}
    if (name === 'translate' || name === 'rotate') {
      if (viewport.software) throw new Error('Canvas 降级模式请使用末端位姿数值输入');
      document.body.classList.remove('hide-control-panel');
      $('#pose-tab').click(); $('.control-content').scrollTop = 0; projectTree.select('target'); $('#drag-mode').value = name;
      $('#drag-mode').dispatchEvent(new Event('change'));
      if ($('#drag-toggle').getAttribute('aria-pressed') !== 'true') $('#drag-toggle').click();
      notice(name === 'translate' ? '已启用末端平移手柄' : '已启用末端旋转手柄'); return;
    }
    if (name === 'configure') {
      await command({type: 'pause'});
      await command({type: 'settings', ...value});
      notice('设置已应用，仿真保持暂停'); return;
    }
    if (name === 'new') {
      await command({type: 'settings', mode: 'kinematic'});
      await command({type: 'reset'}); viewport.fit(); session.syncTarget(); notice('已新建工作区'); return;
    }
    if (name === 'workspace-snapshot') {
      const snapshot = await command({type: 'pause'});
      return {format: 's1-studio-workspace', version: 1, robot: 's1_v1', joints: snapshot.joints,
        gripper: Math.max(0, Math.min(100, snapshot.gripper)), obstacle: snapshot.obstacle,
        camera: {position: viewport.camera.position.toArray(), target: viewport.controls.target.toArray()}};
    }
    if (name === 'workspace-load') {
      await command({type: 'pause'});
      await command({type: 'settings', mode: 'kinematic', obstacle: value.obstacle});
      await command({type: 'joints', joints: value.joints, gripper: value.gripper});
      viewport.camera.position.fromArray(value.camera.position); viewport.controls.target.fromArray(value.camera.target);
      viewport.camera.lookAt(viewport.controls.target); viewport.controls.update(); viewport.invalidate();
      session.syncTarget(); notice('工作区已载入，当前为运动学模式'); return;
    }
    throw new Error('未知工作台操作：' + name);
  }

  async function invoke(name, value) {
    try {
      if ((name === 'translate' || name === 'rotate') && session.ready && $('#drag-toggle').getAttribute('aria-pressed') === 'true' && $('#drag-mode').value === name) {
        $('#drag-toggle').click(); return;
      }
      return await execute(name, value);
    }
    catch (error) {notice(error.message, true); session.message(error.message, true); functionPages.show('activity');}
  }

  $('#settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    $('#settings-save').disabled = true;
    try {
      const next = {...settings, simulation: {
        speed_rad_s: $('#setting-speed').valueAsNumber,
        ik_position_tolerance_mm: $('#setting-position').valueAsNumber,
        ik_orientation_tolerance_deg: $('#setting-orientation').valueAsNumber,
        collision_protection: $('#setting-collision').checked,
        obstacle: $('#setting-obstacle').checked,
      }};
      await desktop.saveSettings(next);
      settingsDialog.close(); notice('设置已保存，下次启动继续使用');
    } catch (error) {$('#settings-result').textContent = error.message;}
    finally {$('#settings-save').disabled = false;}
  });

  if (desktop) {
    desktop.onAction(async ({id, name, value}) => {
      try {const result = await execute(name, value); if (id) desktop.completeAction(id, {ok: true, value: result});}
      catch (error) {notice(error.message, true); if (id) desktop.completeAction(id, {ok: false, message: error.message});}
    });
    const info = await desktop.info();
    await execute('workspace-title', {name: info.workspaceName || 'RoboDK', path: info.workspacePath});
    notice('桌面工作台就绪 · S1 V1 · ' + session.snapshot?.engine);
  } else notice('工作台就绪 · 网页调试模式');
  await functionPages.ready;
  document.body.dataset.workbenchReady = 'true';
}
