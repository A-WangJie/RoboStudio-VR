import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { createRenderer } from '../app/js/renderer.js';
import { StudioError, during } from '../app/js/errors.js';

function canvas(result, failure) {
  const listeners = new Map();
  return {
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: name => listeners.delete(name),
    getContext() {
      if (failure) throw failure;
      if (!result) listeners.get('webglcontextcreationerror')?.({ statusMessage: 'Driver diagnostic' });
      return result;
    },
  };
}

test('confirmed context failure degrades and retains browser diagnostic', () => {
  const renderer = {};
  const selected = createRenderer({ canvas: canvas(null), createCanvas: () => renderer,
    createWebGL: () => assert.fail('WebGL constructor must not run') });
  assert.equal(selected.renderer, renderer);
  assert.equal(selected.software, true);
  assert.equal(selected.degradation.code, 'WEBGL_CONTEXT');
  assert.equal(selected.degradation.cause.message, 'Driver diagnostic');
});

test('renderer constructor bugs are fatal, preserving the original exception', () => {
  const cause = new TypeError('Broken shader initialization');
  assert.throws(() => createRenderer({ canvas: canvas({}), createWebGL: () => { throw cause; },
    createCanvas: () => assert.fail('Must not degrade on a renderer bug') }), error => {
    assert.equal(error.code, 'WEBGL_INIT');
    assert.equal(error.cause, cause);
    return true;
  });
});

test('context API exceptions are not silently degraded', () => {
  const cause = new Error('Unexpected context API exception');
  assert.throws(() => createRenderer({ canvas: canvas(null, cause),
    createCanvas: () => assert.fail('Must not degrade') }), error => error.cause === cause && error.code === 'WEBGL_INIT');
});

test('Canvas initialization failure retains both failure chains', () => {
  const cause = new Error('Canvas 2D unavailable');
  assert.throws(() => createRenderer({ canvas: canvas(null), createCanvas: () => { throw cause; } }), error => {
    assert.equal(error.code, 'CANVAS_INIT');
    assert.equal(error.cause, cause);
    assert.equal(error.degradation.cause.message, 'Driver diagnostic');
    return true;
  });
});

test('successful WebGL selection does not construct Canvas', () => {
  const context = {};
  const selected = createRenderer({ canvas: canvas(context), createWebGL: (element, gl) => {
    assert.equal(gl, context);
    return 'gpu';
  }, createCanvas: () => assert.fail('Unexpected fallback') });
  assert.equal(selected.renderer, 'gpu');
  assert.equal(selected.software, false);
});

test('stage annotation preserves specific model errors and original causes', async () => {
  const cause = new Error('HTTP 404: missing.STL');
  const specific = new StudioError('MODEL_ASSET', 'missing.STL', cause);
  await assert.rejects(during('MODEL_BUILD', 'build failed', () => { throw specific; }), error => error === specific);
  await assert.rejects(during('MODEL_CONFIG', 'model.json', () => { throw cause; }),
    error => error.code === 'MODEL_CONFIG' && error.cause === cause);
});

function bootstrapFile() {
  const elements = new Map();
  const querySelector = selector => {
    if (!elements.has(selector)) elements.set(selector, { hidden: true, style: {}, textContent: '' });
    return elements.get(selector);
  };
  const context = { window: {}, location: { protocol: 'file:' }, performance,
    document: { querySelector, querySelectorAll: () => [],
      body: {classList: {remove() {}}, setAttribute() {}} }, console: { error() {} } };
  // No dynamic import callback is supplied: any attempted module import fails this test.
  vm.runInNewContext(readFileSync(new URL('../app/js/startup.js', import.meta.url), 'utf8'), context);
  return { ...context, querySelector };
}

test('file:// reports an opening-method error before importing modules', () => {
  const page = bootstrapFile();
  assert.equal(page.querySelector('#loading-title').textContent, '打开方式不正确');
  assert.match(page.querySelector('#loading-message').textContent, /start-studio.sh/);
  assert.match(page.querySelector('#error-diagnostic').textContent, /未尝试加载应用模块或初始化 WebGL/);
});

test('model HTTP failures show resource guidance, not browser capability advice', () => {
  const page = bootstrapFile();
  page.window.S1Startup.showError(new StudioError('MODEL_ASSET', 'mesh.STL', new Error('HTTP 404')));
  assert.equal(page.querySelector('#loading-title').textContent, '模型网格加载失败');
  assert.match(page.querySelector('#loading-message').textContent, /网格地址和 HTTP 状态/);
  assert.doesNotMatch(page.querySelector('#loading-message').textContent, /WebGL|浏览器/);
  assert.match(page.querySelector('#error-diagnostic').textContent, /HTTP 404/);
});

test('degradation stays visible and keeps the reason available', () => {
  const page = bootstrapFile();
  page.window.S1Startup.showDegraded(new StudioError('WEBGL_CONTEXT', 'context unavailable', new Error('driver detail')));
  assert.equal(page.querySelector('#render-warning').hidden, false);
  assert.match(page.querySelector('#render-diagnostic').textContent, /driver detail/);
});
