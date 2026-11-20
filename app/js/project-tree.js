import { icon } from './tree-icons.js';
import { functionCategories } from './navigation.js';
import { shortcutVisible, installShortcutMenu } from './project-shortcuts.js';

// This is an object/navigation tree, not a robot program or saved-target list.
export function installProjectTree({invoke}) {
  const tree = document.querySelector('#project-tree');
  const nodes = new Map();
  let currentPage;
  let workspaceFile = {name: 'RoboDK', path: null};
  function navigation(items, keys = [], labels = []) {
    return items.map(item => {
      const path = [...keys, item.id], titles = [...labels, item.label];
      return {id: `nav-${path.join('--')}`, label: item.label,
        icon: item.items ? 'folder' : 'file', navigation: true, shortcutRoute: path.join('/'),
        description: titles.join(' → '),
        ...(item.items ? {children: navigation(item.items, path, titles), expanded: false} : {
          action: 'function-page', value: {id: item.id, keys: path}, page: item.id, route: path.join('/'),
        })};
    });
  }
  const jointNames = ['基座旋转', '肩关节', '肘关节', '腕部俯仰', '腕部偏转', '末端旋转'];
  const objects = [{id: 'workspace', label: 'RoboDK', icon: 'new', expanded: true,
    description: '当前工作区，包含 S1 V1 机械臂、末端目标和工作平面。', children: [
      {id: 'base', label: 'S1 Base（基座坐标系）', icon: 'axes', expanded: true,
        description: 'S1 机械臂的基座参考系。末端位置与姿态输入均以此为参考。', children: [
          {id: 'project-file', label: 'RoboDK（未保存）', icon: 'file', expanded: true,
            action: 'function-page', value: {id: 'model'},
            description: '当前工作区尚未保存。展开功能目录可直接打开对应项目页面。',
            children: navigation(functionCategories())},
          {id: 'robot', label: 'S1 V1', icon: 'robot', expanded: true, action: 'joints',
            description: '六轴机械臂本体。右侧调整关节位置与夹爪开合。', children: [
              {id: 'joints', label: '关节（6）', icon: 'joint-group', expanded: false, action: 'joints',
                description: '展开查看六个关节，选择关节可定位到对应控制项。', children:
                  jointNames.map((name, i) => ({id: `joint-${i + 1}`, label: `J${i + 1}  ${name}`, icon: 'joint', action: 'joints',
                    control: `#joint-value-${i + 1}`, description: `${name}：角度单位为度，输入与滑块受模型关节限位约束。`}))},
              {id: 'gripper', label: '平行夹爪', icon: 'gripper', action: 'gripper',
                description: '双指联动的独立开合量。右侧百分比滑块控制夹爪。'},
              {id: 'tcp', label: 'TCP（模型参考点）', icon: 'axes', action: 'tcp',
                description: '机械臂末端的模型参考点，尚未做实物 TCP 标定。底部显示实际参考点位置。'},
            ]},
          {id: 'target', label: '当前末端目标', icon: 'target', action: 'pose',
            description: '对应当前末端位姿输入和三维拖拽手柄。调整后通过逆解与碰撞检查应用，不是已保存的轨迹点。'},
        ]},
      {id: 'ground', label: 'XY 工作平面', icon: 'grid',
        description: '场景工作平面。顶部网格按钮控制网格显示。'},
    ]}];

  function build(spec, parent, level) {
    const item = document.createElement('li');
    item.className = 'project-item'; item.dataset.node = spec.id;
    if (spec.shortcutRoute) {
      item.dataset.shortcutRoute = spec.shortcutRoute;
      item.hidden = !shortcutVisible(spec.shortcutRoute);
    }
    item.setAttribute('role', 'treeitem'); item.setAttribute('aria-level', level);
    item.setAttribute('aria-selected', 'false'); item.tabIndex = -1;
    const row = document.createElement('div'); row.className = 'project-row';
    const toggle = document.createElement('span'); toggle.className = 'project-toggle'; toggle.setAttribute('aria-hidden', 'true');
    const symbol = document.createElement('span'); symbol.className = `project-icon icon-${spec.icon}`; symbol.innerHTML = icon(spec.icon);
    const label = document.createElement('span'); label.className = 'project-label'; label.id = `tree-label-${spec.id}`; label.textContent = spec.label;
    item.setAttribute('aria-labelledby', label.id);
    row.append(toggle, symbol, label); item.append(row); parent.append(item);
    const entry = {spec, item, row, toggle, label}; nodes.set(spec.id, entry);
    if (spec.children) {
      const group = document.createElement('ul'); group.setAttribute('role', 'group');
      group.hidden = !spec.expanded; entry.group = group;
      item.setAttribute('aria-expanded', String(spec.expanded)); item.append(group);
      spec.children.forEach(child => build(child, group, level + 1));
    }
    row.title = spec.label;
    row.addEventListener('click', event => {
      if (event.target.closest('.project-toggle') && entry.group) {setExpanded(entry, entry.group.hidden); item.focus();}
      else {
        select(entry, {activate: true, focus: true});
        if (spec.navigation && entry.group) setExpanded(entry, entry.group.hidden);
      }
    });
    row.addEventListener('dblclick', event => {
      if (entry.group && !event.target.closest('.project-toggle')) setExpanded(entry, entry.group.hidden);
    });
  }
  objects.forEach(spec => build(spec, tree, 1));

  function select(entry, {activate = false, focus = false} = {}) {
    for (const node of nodes.values()) {
      const selected = node === entry;
      node.item.setAttribute('aria-selected', String(selected)); node.item.tabIndex = selected ? 0 : -1;
    }
    document.querySelector('#tree-selection-name').textContent = entry.label.textContent;
    document.querySelector('#tree-selection-description').textContent = entry.spec.description;
    document.querySelectorAll('.joint-control').forEach(row => row.classList.remove('tree-highlight'));
    if (activate) {
      if (entry.spec.action) invoke(entry.spec.action, entry.spec.value);
      if (entry.spec.control) {
        const row = document.querySelector(entry.spec.control).closest('.joint-control');
        row.classList.add('tree-highlight'); row.scrollIntoView({block: 'nearest'});
      }
      if (entry.spec.id === 'workspace') document.querySelector('.model-details').open = true;
    }
    if (focus) entry.item.focus({preventScroll: true});
  }
  function setExpanded(entry, expanded) {
    if (!entry.group) return;
    if (!expanded && entry.group.querySelector('[aria-selected="true"]')) select(entry);
    entry.group.hidden = !expanded; entry.item.setAttribute('aria-expanded', String(expanded));
  }
  const visibleNodes = () => [...tree.querySelectorAll('[role="treeitem"]')].filter(item => !item.closest('[hidden]'));
  tree.addEventListener('keydown', event => {
    const item = event.target.closest('[role="treeitem"]');
    if (!item) return;
    const entry = nodes.get(item.dataset.node);
    const visible = visibleNodes(), index = visible.indexOf(item);
    let next;
    if (event.key === 'ArrowDown') next = visible[Math.min(index + 1, visible.length - 1)];
    else if (event.key === 'ArrowUp') next = visible[Math.max(index - 1, 0)];
    else if (event.key === 'Home') next = visible[0];
    else if (event.key === 'End') next = visible.at(-1);
    else if (event.key === 'ArrowRight') {
      if (entry.group?.hidden) setExpanded(entry, true);
      else next = [...(entry.group?.children || [])].find(child => !child.hidden);
    } else if (event.key === 'ArrowLeft') {
      if (entry.group && !entry.group.hidden) setExpanded(entry, false);
      else next = item.parentElement.closest('[role="treeitem"]');
    } else if (event.key === 'Enter' || event.key === ' ') {
      select(entry, {activate: true});
      if (entry.spec.navigation && entry.group) setExpanded(entry, entry.group.hidden);
    }
    else return;
    event.preventDefault();
    if (next) select(nodes.get(next.dataset.node), {focus: true});
  });
  function updateFileDescription() {
    const node = nodes.get('project-file');
    node.spec.description = `${workspaceFile.path || '当前工作区尚未保存。'}${currentPage ? '\n当前页面：' + currentPage.labels.join(' → ') : ''}\n展开功能目录可直接跳转页面。`;
    node.row.title = node.spec.description;
    if (node.item.getAttribute('aria-selected') === 'true') document.querySelector('#tree-selection-description').textContent = node.spec.description;
  }
  window.addEventListener('s1:function-page', event => {
    currentPage = event.detail;
    const route = currentPage.keys.join('/');
    for (const entry of nodes.values()) {
      if (!entry.spec.page) continue;
      const active = entry.spec.route === route;
      if (active) {
        entry.item.setAttribute('aria-current', 'page');
        if (shortcutVisible(entry.spec.shortcutRoute)) {
          for (let parent = entry.item.parentElement.closest('[role="treeitem"]'); parent; parent = parent.parentElement.closest('[role="treeitem"]')) setExpanded(nodes.get(parent.dataset.node), true);
        }
      } else entry.item.removeAttribute('aria-current');
    }
    updateFileDescription();
  });
  window.addEventListener('s1:shortcuts-changed', event => {
    let selectionHidden = false, focusHidden = false;
    for (const entry of nodes.values()) {
      if (!entry.spec.shortcutRoute) continue;
      entry.item.hidden = !shortcutVisible(entry.spec.shortcutRoute);
      if (entry.item.hidden) {
        selectionHidden ||= entry.item.getAttribute('aria-selected') === 'true';
        focusHidden ||= entry.item === document.activeElement;
      }
    }
    if (selectionHidden || focusHidden) select(nodes.get('project-file'), {focus: focusHidden});
    if (event.detail?.visible) {
      const entry = nodes.get(`nav-${event.detail.route.replaceAll('/', '--')}`);
      if (entry) {
        for (let parent = entry.item.parentElement.closest('[role="treeitem"]'); parent; parent = parent.parentElement.closest('[role="treeitem"]')) setExpanded(nodes.get(parent.dataset.node), true);
      }
    }
  });
  installShortcutMenu();
  select(nodes.get('robot'));
  return {
    setWorkspaceName(name, path = null) {
      const node = nodes.get('workspace'); node.label.textContent = name; node.row.title = name;
      if (node.item.getAttribute('aria-selected') === 'true') document.querySelector('#tree-selection-name').textContent = name;
      workspaceFile = {name, path};
      const file = nodes.get('project-file');
      file.label.textContent = path ? name : `${name}（未保存）`;
      if (file.item.getAttribute('aria-selected') === 'true') document.querySelector('#tree-selection-name').textContent = file.label.textContent;
      updateFileDescription();
    },
    select(id) {
      const entry = nodes.get(id);
      if (!entry) return;
      for (let parent = entry.item.parentElement.closest('[role="treeitem"]'); parent; parent = parent.parentElement.closest('[role="treeitem"]')) setExpanded(nodes.get(parent.dataset.node), true);
      select(entry);
    },
  };
}
