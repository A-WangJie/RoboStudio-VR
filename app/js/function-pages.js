import { createVRPages } from '/vr-ui/panels.js';
import { toolbarIcon } from './toolbar-icons.js';
import { createArmConfigPages } from './arm-config.js';
import { functionCategories, pageRoutes } from './navigation.js';
import { createFunctionMenu } from './function-menu.js';

export function installFunctionPages({toolbar, activity, settingsDialog, help, invoke}) {
  const $ = s => document.querySelector(s);
  const content = $('.control-content');
  const pages = new Map();
  const categories = functionCategories(), routes = pageRoutes(categories);
  let currentRoute;
  function page(id, title, elements) {
    const section = document.createElement('section'); section.className = 'function-page';
    section.dataset.page = id; section.hidden = true; section.setAttribute('aria-label', title);
    elements.forEach(element => section.append(element)); content.append(section);
    pages.set(id, {section, title}); return section;
  }
  page('joints', '控制 / 关节控制', [$('#joint-panel'), $('.gripper-section')]);
  page('pose', '控制 / 末端位姿', [$('#pose-panel')]);
  const sim = $('.simulation-panel');
  const wrapper = sim.parentElement;
  page('simulation', '仿真 / 运行与碰撞', [sim]); wrapper.remove();
  // Retain the authoritative command buttons; page buttons invoke the same actions.
  const actions = document.createElement('div'); actions.className = 'page-sim-actions';
  for (const [name, label] of [['run','运行动力学'], ['pause','暂停'], ['reset','重置']]) {
    const button = document.createElement('button'); button.textContent = label;
    const source = toolbar.querySelector(`[data-workbench="${name}"]`);
    button.addEventListener('click', () => source.click());
    const sync = () => button.disabled = source.disabled;
    new MutationObserver(sync).observe(source, {attributes: true, attributeFilter:['disabled']}); sync(); actions.append(button);
  }
  sim.querySelector('.sim-actions').hidden = true; $('#simulation-reset').hidden = true;
  sim.querySelector('.sim-label').after(actions);
  page('activity', '数据 / 事件记录', [activity]);
  const model = $('.model-details'); model.open = true;
  page('model', '数据 / 项目与模型信息', [model]);
  page('settings', '设置 / 工作台参数', [settingsDialog]);
  page('help', '帮助 / 使用说明', [help]);
  const armPages = createArmConfigPages();
  for (const id of ['xr-connection','xr-guide','arm-ar']) armPages.delete(id);
  for (const [id, configPage] of createVRPages()) armPages.set(id,configPage);
  for (const [id, configPage] of armPages) page(id, `${id.startsWith('teaching-') ? '从臂示教模块' : id.startsWith('capture-') ? '数据采集' : id === 'arm-ar' || id.startsWith('xr-') ? 'AR / VR' : '机械臂配置'} / ${configPage.title}`, [configPage.root]);
  $('.control-tabs').hidden = true;
  $('.control-footnote').hidden = true; $('.phase-note').hidden = true;
  const heading = $('.control-panel > .panel-title');
  let current = 'joints';
  function show(id, keys) {
    if (!pages.has(id)) return;
    currentRoute = routes.find(route => route.id === id && route.keys.join('/') === (keys || (currentRoute?.id === id ? currentRoute.keys : [])).join('/')) || routes.find(route => route.id === id);
    current = id;
    document.body.classList.remove('hide-control-panel');
    for (const [key, value] of pages) value.section.hidden = key !== id;
    heading.textContent = currentRoute?.labels.join(' / ') || pages.get(id).title;
    heading.title = heading.textContent;
    pages.get(id).section.setAttribute('aria-label', heading.textContent);
    document.body.dataset.currentFunctionPage = id;
    content.scrollTop = 0;
    if (id === 'joints') $('#joint-panel').hidden = false;
    if (id === 'pose') $('#pose-panel').hidden = false;
    if (id === 'activity') activity.hidden = false;
    if (id === 'model') model.open = true;
    document.querySelectorAll('[data-function-page]').forEach(b => b.setAttribute('aria-current', String(b.dataset.functionPage === id && b.dataset.functionRoute === currentRoute?.keys.join('/'))));
    window.dispatchEvent(new CustomEvent('s1:function-page', {detail: currentRoute || {id, keys: [], labels: [pages.get(id).title]}}));
  }
  $('#joint-tab').addEventListener('click', () => show('joints'));
  content.addEventListener('click', event => {
    const target = event.target.closest('[data-open-function]');
    if (target) show(target.dataset.openFunction);
  });
  $('#pose-tab').addEventListener('click', () => show('pose'));
  $('#close-activity').addEventListener('click', () => show('joints'));
  settingsDialog.addEventListener('close', () => {if(current === 'settings') show('joints');});
  help.addEventListener('close', () => {if(current === 'help') show('joints');});
  $('#project-tree').addEventListener('click', e => {
    if (!e.target.closest('.project-toggle') && ['workspace','base','ground'].includes(e.target.closest('[data-node]')?.dataset.node)) show('model');
  });
  $('#project-tree').addEventListener('keydown', e => {
    if (['Enter',' '].includes(e.key) && ['workspace','base','ground'].includes(e.target.closest('[data-node]')?.dataset.node)) show('model');
  });
  function open(id, keys) {
    show(id, keys);
    if (id === 'settings' || id === 'help') invoke(id);
  }
  const {menu, show: showMenu, close} = createFunctionMenu({open, current: () => currentRoute});
  for (const category of categories) {
    const {id, label, icon: symbol} = category;
    const button = document.createElement('button'); button.className = 'function-category'; button.dataset.category = id;
    button.dataset.shortcutRoute = id;
    button.innerHTML = toolbarIcon(symbol) + `<span>${label}</span><span class="category-arrow">▾</span>`;
    button.setAttribute('aria-label', label); button.setAttribute('aria-haspopup', 'menu'); button.setAttribute('aria-expanded', 'false'); button.title = `展开${label}功能`;
    button.addEventListener('click', () => showMenu(button, category));
    button.addEventListener('keydown', event => {if (event.key === 'ArrowDown') {event.preventDefault(); if (button.getAttribute('aria-expanded') !== 'true') button.click(); else menu.querySelector('button')?.focus();}});
    if(id === 'simulation') {
      button.classList.add('simulation-dropdown');button.innerHTML='<span class="category-arrow">▾</span>';
      button.setAttribute('aria-label','选择仿真模式');button.title='选择仿真模式';
      const primary=document.createElement('button');primary.className='function-category simulation-primary';
      primary.dataset.simulationPrimary='true';
      primary.dataset.shortcutRoute = id;
      const run=toolbar.querySelector('[data-workbench="run"]'),pause=toolbar.querySelector('[data-workbench="pause"]');
      primary.innerHTML=toolbarIcon('play')+'<span>仿真</span>';primary.title='开始动力学仿真';primary.setAttribute('aria-label',primary.title);
      const sync=()=>{primary.disabled=run.disabled;};
      primary.addEventListener('click',()=>{close();run.click();});
      for(const source of [run,pause])new MutationObserver(sync).observe(source,{attributes:true,attributeFilter:['disabled']});sync();
      const split=document.createElement('div');split.className='simulation-split';split.setAttribute('role','group');split.setAttribute('aria-label','仿真');split.append(primary,button);toolbar.append(split);
      button.addEventListener('click',()=>{
        if(menu.hidden)return;
        const select=$('#simulation-mode');
        for(const option of [...select.options].reverse()){
          const entry=document.createElement('button');entry.textContent=option.textContent;entry.setAttribute('role','menuitemradio');entry.setAttribute('aria-checked',String(select.value===option.value));entry.disabled=select.disabled;
          entry.addEventListener('click',()=>{close(true);select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));});menu.prepend(entry);
        }
        menu.firstElementChild.focus();
      });
    } else toolbar.append(button);
    if (id === 'arm-config' || id === 'control' || id === 'capture') {
      const fileGroup = toolbar.querySelector('.tool-group[aria-label="文件与工作区"]');
      fileGroup.classList.remove('desktop-only'); fileGroup.append(button);
    }
    if (id === 'simulation') {
      // Reuse the authoritative controls so disabled state and commands stay shared.
      const group=toolbar.querySelector('.tool-group[aria-label="动力学仿真"]');
      group.querySelector('[data-workbench="run"]').hidden=true;group.querySelector('[data-workbench="pause"]').hidden=false;
      toolbar.append(group);
    }
  }
  toolbar.addEventListener('scroll', () => close());
  for(const group of toolbar.querySelectorAll('.tool-group')) {
    if(['机械臂与末端控制','工具与帮助'].includes(group.getAttribute('aria-label'))) group.hidden=true;
  }
  show('joints');
  return {show, open, categories, ready: armPages.ready};
}
