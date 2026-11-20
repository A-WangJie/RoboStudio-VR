// Reparent existing controls so their event handlers and live values stay intact.
export function installWorkspaceLayout() {
  const $ = selector => document.querySelector(selector);
  const scene = $('.scene-panel');
  const controls = $('.control-panel');
  const content = $('.control-content');

  const simulation = document.createElement('details');
  simulation.className = 'inspector-section';
  simulation.open = true;
  const simulationTitle = document.createElement('summary');
  simulationTitle.textContent = '仿真与碰撞';
  simulation.append(simulationTitle, $('.simulation-panel'));

  const model = $('.model-details');
  model.classList.add('inspector-section');
  model.querySelector('summary').textContent = '项目与模型信息';
  model.querySelector('summary').after($('.tree-selection'));
  content.append(simulation, model, $('.phase-note'));
  content.append($('.control-footnote'));

  scene.querySelector('.panel-title').remove();
  scene.setAttribute('aria-label', '项目树');
  $('#viewport').append(scene);

  const dock = document.createElement('div');
  dock.className = 'control-dock';
  controls.before(dock);
  controls.id = 'control-drawer';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.id = 'control-drawer-toggle';
  toggle.className = 'control-drawer-toggle';
  toggle.setAttribute('aria-controls', controls.id);
  toggle.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg><span>收起</span>';
  dock.append(toggle, controls);
  toggle.addEventListener('click', () => document.body.classList.toggle('hide-control-panel'));

  // The native View menu and object/toolbar navigation use this same body class.
  function syncDrawer() {
    const collapsed = document.body.classList.contains('hide-control-panel');
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.setAttribute('aria-label', collapsed ? '展开控制侧栏' : '收起控制侧栏');
    toggle.title = collapsed ? '展开控制侧栏' : '收起控制侧栏';
    toggle.querySelector('span').textContent = collapsed ? '控制' : '收起';
    controls.inert = collapsed;
    if (collapsed && controls.contains(document.activeElement)) toggle.focus({preventScroll: true});
  }
  new MutationObserver(syncDrawer).observe(document.body, {attributes: true, attributeFilter: ['class']});
  syncDrawer();

  const readout = $('.readout');
  const status = $('.statusbar');
  readout.setAttribute('role', 'region');
  readout.setAttribute('aria-label', '末端坐标与工作台状态');
  status.before(readout);
  readout.append(status);

  // Non-actuating tree objects reveal their information in the right inspector.
  $('#project-tree').addEventListener('click', event => {
    if (event.target.closest('.project-toggle')) return;
    revealObjectInfo(event.target.closest('[role="treeitem"]'));
  });
  $('#project-tree').addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') revealObjectInfo(event.target.closest('[role="treeitem"]'));
  });
  function revealObjectInfo(item) {
    if (!['workspace', 'base', 'ground'].includes(item?.dataset.node)) return;
    document.body.classList.remove('hide-control-panel');
    model.open = true;
    model.scrollIntoView({block: 'nearest'});
  }
}
