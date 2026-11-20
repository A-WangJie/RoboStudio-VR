// Available before scene startup, including the desktop loading/error screen.
(() => {
  const desktop = window.s1Desktop;
  const bar = document.createElement('header');
  bar.id = 'app-titlebar';
  bar.setAttribute('aria-label', 'RoboStudio 标题栏');
  bar.innerHTML = `<div class="wordmark" aria-label="RoboStudio">Robo<span>Studio</span></div>
    <div class="window-controls" role="group" aria-label="窗口控制" hidden>
      <button type="button" data-window-action="minimize" aria-label="最小化" title="最小化"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5h10"/></svg></button>
      <button type="button" data-window-action="maximize" aria-label="最大化" title="最大化"><svg class="maximize-symbol" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9"/></svg><svg class="restore-symbol" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 5V2.5h7.5V10H11"/><rect x="2.5" y="5.5" width="8" height="8"/></svg></button>
      <button type="button" data-window-action="close" aria-label="关闭窗口" title="关闭窗口"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 3.5 9 9m0-9-9 9"/></svg></button>
    </div>`;
  document.body.prepend(bar);
  if (!desktop?.windowAction) return;
  bar.querySelector('.window-controls').hidden = false;
  const sync = ({maximized}) => {
    bar.dataset.maximized = String(maximized);
    const button = bar.querySelector('[data-window-action="maximize"]');
    button.title = maximized ? '还原窗口' : '最大化';
    button.setAttribute('aria-label', button.title);
  };
  desktop.onWindowState(sync);
  desktop.windowState().then(sync).catch(console.error);
  bar.querySelectorAll('[data-window-action]').forEach(button => {
    button.addEventListener('click', () => desktop.windowAction(button.dataset.windowAction).catch(console.error));
  });
})();
