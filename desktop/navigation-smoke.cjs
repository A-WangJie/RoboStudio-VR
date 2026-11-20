// Exercises file identity through the real Electron dialogs/IPC in a test profile.
const fs = require('node:fs');
const path = require('node:path');
const {dialog} = require('electron');

module.exports = async ({js, wait, check, screenshot, configPath, root, fileAction, window}) => {
  const result = await js(fs.readFileSync(path.join(root, 'tests/browser-navigation.js'), 'utf8'));
  check(result.ok, result.error || 'Desktop multilevel navigation works');
  for (const message of result.checks) check(true, message);
  await screenshot('navigation-desktop-menu.png');
  await js(`document.querySelector('.function-menu').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`);
  const savedPath = path.join(path.dirname(configPath), 'navigation project.s1studio');
  const openedPath = path.join(path.dirname(configPath), 'opened project.s1studio');
  const originalSave = dialog.showSaveDialog, originalOpen = dialog.showOpenDialog, originalMessage = dialog.showMessageBox;
  try {
    dialog.showSaveDialog = async () => ({canceled: false, filePath: savedPath});
    await fileAction('save-as');
    await wait(() => js(`document.querySelector('#tree-label-project-file').textContent === 'navigation project.s1studio'`));
    check(await js(`document.querySelector('[data-node="project-file"] > .project-row').title.includes(${JSON.stringify(savedPath)})`), '另存后项目树同步文件名和真实路径');
    fs.copyFileSync(savedPath, openedPath);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [openedPath]});
    await fileAction('open');
    await wait(() => js(`document.querySelector('#tree-label-project-file').textContent === 'opened project.s1studio'`));
    check((await js('window.s1Desktop.info()')).workspacePath === openedPath, '打开工作区后桌面IPC提供当前文件路径');
    check(await js(`document.querySelector('[data-node="project-file"] > .project-row').title.includes(${JSON.stringify(openedPath)})`), '打开其他文件后项目树替换旧路径');
    await js(`document.querySelector('[data-node="project-file"] > .project-row').click()`);
    check(await js(`document.querySelector('#tree-selection-description').textContent.includes(${JSON.stringify(openedPath)}) && document.body.dataset.currentFunctionPage === 'model'`), '文件节点可跳转项目页并显示当前文件路径');
    await screenshot('navigation-project.png');
    dialog.showOpenDialog = async () => ({canceled: true, filePaths: []});
    await fileAction('open');
    check((await js('window.s1Desktop.info()')).workspacePath === openedPath, '取消打开保留当前文件关联');
    dialog.showMessageBox = async () => ({response: 1});
    await fileAction('new');
    await wait(() => js(`document.querySelector('#tree-label-project-file').textContent === 'RoboDK（未保存）'`));
    check(!(await js('window.s1Desktop.info()')).workspacePath && await js(`!document.querySelector('[data-node="project-file"] > .project-row').title.includes(${JSON.stringify(openedPath)})`), '新建项目清除旧文件路径并恢复未保存状态');
  } finally {
    dialog.showSaveDialog = originalSave; dialog.showOpenDialog = originalOpen; dialog.showMessageBox = originalMessage;
  }
  const shortcuts = await js(fs.readFileSync(path.join(root, 'tests/browser-shortcuts.js'), 'utf8'));
  check(shortcuts.ok, shortcuts.error || 'Desktop shortcut management works');
  for (const message of shortcuts.checks) check(true, message);
  await screenshot('project-shortcuts-desktop.png');
  {
    await wait(async () => {
      const saved = await js('window.s1Desktop.projectShortcuts()');
      return saved.includes('capture') && saved.includes('data') && !saved.includes('control');
    });
    check(fs.existsSync(path.join(path.dirname(configPath), 'project-shortcuts.json')), '桌面快捷偏好写入独立配置文件');
    // Empty origin storage to prove restoration comes from the desktop config.
    await js("localStorage.removeItem('robostudio.project-shortcuts.v1')");
    await new Promise(resolve => {window.webContents.once('did-finish-load', resolve); window.reload();});
    await wait(() => js('document.body.dataset.workbenchReady === "true" && document.querySelector("#loading").hidden'));
    check(await js(`document.querySelector('[data-node="nav-capture"]').hidden && document.querySelector('[data-node="nav-data"]').hidden && !document.querySelector('[data-node="nav-control"]').hidden`), '桌面重新加载后保留快捷目标栏显示选择');
    await js(`document.querySelector('[data-category="data"]').click(); document.querySelector('[data-function-page="model"]').click()`);
    check(await js(`document.querySelector('[data-node="nav-data"]').hidden && document.body.dataset.currentFunctionPage === 'model'`), '桌面重载后隐藏功能仍可从工具栏使用且不会自动加回');
  }
};
