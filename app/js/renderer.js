import { StudioError } from './errors.js';

// Only a confirmed failure to acquire WebGL2 permits automatic degradation.
// Renderer construction errors after acquisition are programming/runtime errors.
export function createRenderer({ canvas, createWebGL, createCanvas }) {
  let context;
  let contextMessage = '';
  const onError = event => { contextMessage = event.statusMessage || ''; };
  canvas.addEventListener('webglcontextcreationerror', onError);
  try {
    context = canvas.getContext('webgl2', { antialias: true, alpha: true });
  } catch (cause) {
    throw new StudioError('WEBGL_INIT', '获取 WebGL2 上下文时发生异常', cause);
  } finally {
    canvas.removeEventListener('webglcontextcreationerror', onError);
  }
  if (!context) {
    const reason = new StudioError('WEBGL_CONTEXT', '无法创建 WebGL2 上下文',
      new Error(contextMessage || 'canvas.getContext("webgl2") 返回 null；浏览器未提供进一步原因'));
    console.warn('[WEBGL_CONTEXT] 启用 Canvas 降级模式；具体原因需查看浏览器诊断。', reason);
    try {
      return { renderer: createCanvas(), software: true, degradation: reason };
    } catch (cause) {
      const error = new StudioError('CANVAS_INIT', 'WebGL2 上下文不可用，Canvas 兼容渲染器也初始化失败', cause);
      error.degradation = reason;
      throw error;
    }
  }
  try {
    return { renderer: createWebGL(canvas, context), software: false, degradation: null };
  } catch (cause) {
    throw new StudioError('WEBGL_INIT', 'WebGL2 上下文已创建，但三维渲染器初始化失败', cause);
  }
}
