// Classic script deliberately runs before module loading, including under file://.
(() => {
  const startedAt = performance.now();
  let failed = false;
  const $ = selector => document.querySelector(selector);
  const guidance = {
    FILE_PROTOCOL: ['打开方式不正确', '请运行项目中的 start-studio.sh，然后在 Google Chrome 打开终端显示的 http://127.0.0.1 地址。直接双击 HTML 可能被文件协议的模块与资源访问限制阻止。'],
    MODULE_LOAD: ['应用模块加载失败', '请检查本地服务是否运行、js/ 与 vendor/ 文件是否完整，并在 Chrome 控制台查看具体模块地址。'],
    WEBGL_INIT: ['三维渲染初始化异常', '请查看下方原始错误及 Chrome 控制台。此异常没有自动降级；需根据具体错误排查渲染代码、浏览器或图形环境。'],
    CANVAS_INIT: ['兼容渲染初始化失败', 'WebGL2 上下文与 Canvas 初始化均未成功。请查看下方两项诊断和 Chrome 控制台。'],
    MODEL_CONFIG: ['模型配置加载失败', '请检查显示的 model.json 地址、HTTP 状态及 JSON 内容，确认本地模型资源完整。'],
    MODEL_ASSET: ['模型网格加载失败', '请检查下方网格地址和 HTTP 状态，确认文件存在且可通过本地服务读取。'],
    MODEL_PARSE: ['模型网格解析失败', '文件已读取，但无法解析为有效 STL。请检查下方网格地址及文件内容。'],
    MODEL_BUILD: ['模型结构初始化失败', '请检查模型中的关节、连杆层级及网格引用，并查看 Chrome 控制台中的原始错误。'],
    SCENE_INIT: ['场景初始化异常', '请查看下方原始错误及 Chrome 控制台，按具体异常检查场景和界面代码。'],
    RENDER_FRAME: ['场景渲染异常', '渲染已停止。请查看下方原始错误和 Chrome 控制台，检查渲染代码及图形运行状态。'],
  };
  function diagnostic(error) {
    const lines = [];
    const seen = new Set();
    for (let current = error; current && !seen.has(current); current = current.cause) {
      seen.add(current);
      lines.push(current.stack || String(current));
    }
    if (error?.degradation) lines.push('初始 WebGL 诊断：', diagnostic(error.degradation));
    return lines.join('\n原因：\n');
  }
  function showError(error) {
    failed = true;
    document.body.classList.remove('studio-revealing');
    console.error(`[${error.code || 'UNEXPECTED'}] S1 Studio 启动或运行失败`, error);
    const [title, action] = guidance[error.code] || ['应用发生异常', '请查看下方原始错误和 Chrome 控制台，按具体异常排查。'];
    document.querySelectorAll('button:not([data-window-action]),input').forEach(element => { element.disabled = true; });
    document.body.setAttribute('aria-busy', 'false');
    $('#loading').hidden = false;
    $('#loading .spinner').hidden = true;
    $('#loading-title').textContent = title;
    $('#loading-message').textContent = action;
    $('#error-details').hidden = false;
    $('#error-diagnostic').textContent = diagnostic(error);
    $('#status-text').textContent = `${title} · ${error.code || 'UNEXPECTED'}`;
    $('#status-dot').style.background = '#ef8e8e';
  }
  function showDegraded(reason) {
    $('#render-warning').hidden = false;
    $('#render-diagnostic').textContent = diagnostic(reason);
    $('#status-dot').style.background = '#edbd75';
  }
  function progress(title, message) {
    $('#loading-title').textContent = title;
    $('#loading-message').textContent = message;
  }
  async function ready() {
    await document.fonts.ready;
    // Keep fast startups calm; slow startups wait only for actual readiness.
    await new Promise(resolve => setTimeout(resolve, Math.max(350, 1800 - (performance.now() - startedAt))));
    if (failed) return;
    document.body.classList.remove('studio-starting');
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (failed) return;
    document.body.classList.add('studio-revealing');
    await new Promise(resolve => setTimeout(resolve, 300));
    if (failed) return;
    $('#loading').hidden = true;
    document.body.classList.remove('studio-revealing');
    document.body.setAttribute('aria-busy', 'false');
  }
  window.S1Startup = Object.freeze({ showError, showDegraded, progress, ready });
  document.querySelectorAll('button:not([data-window-action]),input').forEach(element => { element.disabled = true; });
  if (location.protocol === 'file:') {
    const error = new Error('当前地址使用 file://；未尝试加载应用模块或初始化 WebGL。');
    error.code = 'FILE_PROTOCOL';
    showError(error);
    return;
  }
  import('./main.js').then(module => module.start()).catch(error => {
    if (!error.code) {
      const wrapped = new Error('应用入口或依赖模块加载失败', { cause: error });
      wrapped.code = 'MODULE_LOAD';
      showError(wrapped);
    } else showError(error);
  });
})();
