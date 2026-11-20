(async () => {
  const $ = selector => document.querySelector(selector), checks = [];
  const assert = (condition, message) => {if (!condition) throw Error(message); checks.push(message);};
  const wait = async predicate => {
    for (let i=0; i<180; i++) {if (await predicate()) return; await new Promise(resolve => setTimeout(resolve, 50));}
    throw Error('等待导航状态超时');
  };
  const tree = id => $(`[data-node="${id}"]`);
  const open = (branch, page) => {
    $('[data-category="control"]').click();
    $(`.function-menu [data-subcategory="${branch}"]`).click();
    $(`.function-menu [data-function-page="${page}"]`).click();
  };
  const result = {ok: false, checks};
  try {
    await wait(() => document.body.dataset.workbenchReady === 'true' && $('#loading').hidden);
    const before = await (await fetch('/api/sim/state')).json();
    assert($('[data-category="arm-config"]').nextElementSibling === $('[data-category="control"]'), '机械臂控制紧邻机械臂配置右侧');
    assert($('[data-category="control"]').textContent.includes('机械臂控制') && !$('#workbench-toolbar [data-category="xr"]') && !$('#workbench-toolbar [data-category="teaching"]'), '三个控制入口合并为同一工具栏分类');
    $('[data-category="control"]').click();
    const menu = $('.function-menu');
    assert([...menu.querySelectorAll('[data-subcategory]')].map(b => b.dataset.subcategory).join(',') === 'teaching,mouse,xr', '二级分类按从臂示教、鼠标控制、AR/VR排序');
    assert([...menu.querySelectorAll('.function-submenu')].every(group => group.hidden), '三级功能默认折叠，通过箭头展开');
    const beforeExpand = document.body.dataset.currentFunctionPage;
    const teaching = menu.querySelector('[data-subcategory="teaching"]'); teaching.focus();
    teaching.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
    assert(teaching.getAttribute('aria-expanded') === 'true' && document.activeElement.dataset.functionPage === 'teaching-session', '右方向键展开三级功能并进入第一个功能');
    assert(document.body.dataset.currentFunctionPage === beforeExpand, '展开分类不会切换页面');
    menu.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}));
    assert(teaching.getAttribute('aria-expanded') === 'false' && document.activeElement === teaching, '左方向键折叠并返回二级分类');
    teaching.click(); menu.querySelector('[data-function-page="teaching-session"]').click();
    assert(!$('.function-page[data-page="teaching-session"]').hidden && menu.hidden, '选择三级功能打开已有示教页面');
    const activeTeaching = tree('nav-control--teaching--teaching-session');
    assert(activeTeaching.getAttribute('aria-current') === 'page' && !activeTeaching.closest('[hidden]'), '项目树随页面变化展开对应分支并标记当前页');
    assert(tree('project-file').parentElement.closest('[data-node]').dataset.node === 'base', '当前项目文件位于S1 Base下面');
    assert($('#tree-label-project-file').textContent.includes('未保存'), '尚未保存的项目明确显示未保存');
    open('mouse', 'pose');
    $('#pose-x').value = '123.45';
    for (const [branch, ids] of [
      ['teaching', ['teaching-mapping', 'teaching-guide', 'arm-teaching']],
      ['xr', ['xr-connection', 'xr-control', 'xr-data', 'xr-guide']],
      ['mouse', ['joints', 'pose']],
    ]) for (const id of ids) {
      open(branch, id);
      assert(document.body.dataset.currentFunctionPage === id && $(`.function-page[data-page="${id}"]`).hidden === false, `原有页面可从三级菜单打开：${id}`);
    }
    assert($('#pose-x').value === '123.45', '跨分类切换保留原页面输入，不复制或重建控件');
    const pair = tree('nav-control--teaching--arm-teaching');
    pair.querySelector('.project-row').click();
    assert(document.body.dataset.currentFunctionPage === 'arm-teaching' && $('.control-panel > .panel-title').textContent.includes('从臂示教'), '项目树直接打开示教配对页并保留分类归属');
    tree('nav-arm-config--arm-teaching').querySelector('.project-row').click();
    assert($('.control-panel > .panel-title').textContent.startsWith('机械臂配置'), '共享页面从配置入口打开时显示对应路径');
    const poseNode = tree('nav-control--mouse--pose'); poseNode.focus();
    poseNode.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    assert(document.body.dataset.currentFunctionPage === 'pose' && poseNode.getAttribute('aria-current') === 'page', '项目树支持Enter跳转已有页面');
    tree('nav-control--mouse').querySelector('.project-toggle').click();
    assert(tree('nav-control--mouse').getAttribute('aria-expanded') === 'false' && document.body.dataset.currentFunctionPage === 'pose', '折叠树目录不会切换页面');
    tree('project-file').querySelector('.project-row').click();
    assert(document.body.dataset.currentFunctionPage === 'model' && $('#tree-selection-description').textContent.includes('当前页面'), '点击当前项目打开项目页，显示文件和当前页面关系');
    $('[data-category="control"]').click();
    $('.function-menu').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    assert(menu.hidden && document.activeElement === $('[data-category="control"]'), 'Esc关闭多级菜单并返回工具栏');
    $('[data-category="control"]').click();
    document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
    assert(menu.hidden, '点击菜单外部正常关闭');
    assert((await (await fetch('/api/sim/state')).json()).command_count === before.command_count, '全部分类、目录和页面跳转均未下发机械臂命令');
    open('mouse', 'pose');
    $('[data-category="control"]').click();
    for (const button of menu.querySelectorAll('[data-subcategory]')) button.click();
    result.ok = true;
  } catch (error) {result.error = error.stack;}
  const output = document.createElement('pre'); output.id = 'test-result'; output.hidden = true;
  output.textContent = JSON.stringify(result); document.body.append(output);
  return result;
})();
