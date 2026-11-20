(async () => {
  const $ = selector => document.querySelector(selector), checks = [];
  const assert = (condition, message) => {if (!condition) throw Error(message); checks.push(message);};
  const wait = async predicate => {
    for (let i=0; i<180; i++) {if (await predicate()) return; await new Promise(resolve => setTimeout(resolve, 50));}
    throw Error('等待快捷目标栏状态超时');
  };
  const node = route => $(`[data-node="nav-${route.replaceAll('/', '--')}"]`);
  const row = route => node(route).querySelector('.project-row');
  const context = element => element.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX:120, clientY:210, button:2}));
  const menu = () => $('#shortcut-context-menu');
  const choose = expected => {
    const action = menu().querySelector('button');
    assert(action.dataset.shortcutAction === expected, `右键操作显示${expected === 'add' ? '添加' : '移出'}`);
    action.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true})); action.click();
  };
  const result = {ok:false, checks};
  try {
    await wait(() => document.body.dataset.workbenchReady === 'true' && $('#loading').hidden);
    if (sessionStorage.getItem('shortcut-reload') === 'pending') {
      checks.push(...JSON.parse(sessionStorage.getItem('shortcut-checks')));
      assert(node('capture').hidden && node('data').hidden, '刷新后恢复已移出的快捷目录');
      assert(!node('control').hidden && !node('control/mouse/pose').hidden, '刷新后保留其他快捷目录和恢复过的功能');
      $('[data-category="data"]').click(); $('[data-function-page="model"]').click();
      assert(node('data').hidden, '刷新后打开隐藏目录内页面仍不会把目录重新加回');
      assert((await (await fetch('/api/sim/state')).json()).command_count === Number(sessionStorage.getItem('shortcut-command-count')), '刷新恢复和页面访问未发送机械臂命令');
      sessionStorage.removeItem('shortcut-reload');
      context($('[data-category="data"]'));
    } else {
      const before = await (await fetch('/api/sim/state')).json();
      const page = document.body.dataset.currentFunctionPage;
      row('capture').click();
      context(row('capture')); choose('remove');
      assert(node('capture').hidden && document.body.dataset.currentFunctionPage === page, '树中移出文件夹仅隐藏快捷入口，不改变当前功能');
      assert($('[data-node="project-file"]').getAttribute('aria-selected') === 'true' && $('#project-tree [tabindex="0"]')?.closest('[hidden]') === null, '移出选中目录后选择回到可见项目节点');
      assert(!!$('[data-category="capture"]'), '移出后工具栏保留原功能');
      context($('[data-category="capture"]')); choose('add');
      assert(!node('capture').hidden, '工具栏右键可重新添加文件夹');
      // Remove a leaf and then its parent; restoring another leaf must not erase that preference.
      $('[data-category="control"]').click(); $('[data-subcategory="mouse"]').click();
      const pose = $('.function-menu [data-function-page="pose"]');
      context(pose); choose('remove');
      assert(node('control/mouse/pose').hidden && !$('.function-menu').hidden, '三级功能可单独移出，操作后保留展开菜单');
      context($('[data-category="control"]')); choose('remove');
      assert(node('control').hidden && node('control/mouse').hidden, '移出父目录同时隐藏其子目录');
      // Open the same page through the toolbar without bringing shortcuts back.
      pose.click();
      assert(document.body.dataset.currentFunctionPage === 'pose' && node('control').hidden, '移出后原功能仍可用，页面切换不会恢复隐藏目录');
      $('[data-category="control"]').click(); $('[data-subcategory="mouse"]').click();
      context($('.function-menu [data-function-page="joints"]')); choose('add');
      assert(!node('control').hidden && !node('control/mouse/joints').hidden && node('control/mouse/pose').hidden, '添加子功能恢复所需父目录，保留其他子项隐藏选择');
      context($('.function-menu [data-function-page="pose"]')); choose('add');
      assert(!node('control/mouse/pose').hidden && $('[data-node="project-file"]').getAttribute('aria-expanded') === 'true', '重新添加具体功能后展开可访问路径');
      context($('.function-menu [data-subcategory="xr"]')); choose('remove');
      assert(node('control/xr').hidden && !node('control/mouse').hidden, '二级分类可独立移出，不影响其他控制分类');
      context($('.function-menu [data-subcategory="xr"]')); choose('add');
      document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true}));
      const data = $('[data-category="data"]'); data.focus();
      data.dispatchEvent(new KeyboardEvent('keydown', {key:'F10', shiftKey:true, bubbles:true, cancelable:true}));
      assert(!menu().hidden && menu().querySelector('button') === document.activeElement, 'Shift+F10可打开快捷管理菜单');
      menu().dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true, cancelable:true}));
      assert(menu().hidden && document.activeElement === data, 'Esc关闭右键菜单并恢复焦点');
      context(data); document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true}));
      assert(menu().hidden, '点击外部关闭右键菜单');
      context($('[data-node="robot"] > .project-row'));
      assert(menu().hidden && !$('[data-node="robot"]').hidden, '机械臂实体节点不作为可移出的快捷功能');
      for (const id of ['capture','data']) {context($(`[data-category="${id}"]`)); choose('remove');}
      const saved = JSON.parse(localStorage.getItem('robostudio.project-shortcuts.v1'));
      assert(saved.includes('capture') && saved.includes('data') && !saved.includes('control'), '快捷目录选择已保存');
      assert((await (await fetch('/api/sim/state')).json()).command_count === before.command_count, '右键菜单及添加移出操作没有下发机械臂命令');
      if (!window.s1Desktop) {
        sessionStorage.setItem('shortcut-reload', 'pending');
        sessionStorage.setItem('shortcut-checks', JSON.stringify(checks));
        sessionStorage.setItem('shortcut-command-count', before.command_count);
        location.reload(); return;
      }
      context(data);
    }
    result.ok = true;
  } catch (error) {result.error = error.stack;}
  const output = document.createElement('pre'); output.id='test-result'; output.hidden=true;
  output.textContent=JSON.stringify(result); document.body.append(output); return result;
})();
