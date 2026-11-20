import { RobotState } from './state.js';
import { RobotModel } from './robot.js';
import { Viewport } from './viewport.js';
import { StudioError, during } from './errors.js';
import { Teleop } from './teleop.js';
import { installWorkbench } from './workbench.js';
import { HardwareMouse } from './hardware-mouse.js';

const $ = selector => document.querySelector(selector);
const degrees = radians => radians * 180 / Math.PI;
const radians = degrees => degrees * Math.PI / 180;
const setFill = (slider, value, min, max) => slider.style.setProperty('--fill', `${(value - min) / (max - min) * 100}%`);

export async function start() {
  let viewport;
  try {
    await initialize(value => { viewport = value; });
  } catch (error) {
    viewport?.stop();
    if (error instanceof StudioError) throw error;
    throw new StudioError('SCENE_INIT', '场景或界面初始化失败', error);
  }
}

async function initialize(onViewport) {
  const interactive = [...document.querySelectorAll('button:not([data-window-action]),input')];
  interactive.forEach(element => element.disabled = true);
  const viewport = await during('SCENE_INIT', '三维场景初始化失败', () => new Viewport($('#viewport')));
  onViewport(viewport);
  const url = new URL('../assets/s1_v1/model.json', import.meta.url);
  const specification = await during('MODEL_CONFIG', `读取模型配置：${url.href}`, async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}: ${url.href}`);
    return response.json();
  });
  const state = await during('MODEL_BUILD', '初始化关节配置失败', () => new RobotState(specification));
  const robot = await during('MODEL_BUILD', '构建模型层级失败', () => new RobotModel(specification).load(new URL('.', url)));
  await during('MODEL_BUILD', '设置模型姿态或视图失败', () => {
    robot.apply(state);
    viewport.attach(robot);
  });
  const names = ['基座旋转', '肩关节', '肘关节', '腕部俯仰', '腕部偏转', '末端旋转'];
  let session;
  const rows = state.joints.map((joint, index) => {
    const [min, max] = joint.limits.map(degrees);
    const row = document.createElement('div');
    row.className = 'joint-control';
    row.innerHTML = `<div class="joint-top"><label class="joint-badge" for="joint-${index + 1}">J${index + 1}</label><span class="joint-name">${names[index]}</span><label class="joint-input"><input id="joint-value-${index + 1}" type="number" aria-label="J${index + 1} 角度" min="${min}" max="${max}" step="0.1"><span>°</span></label></div><input id="joint-${index + 1}" type="range" min="${min}" max="${max}" step="any" aria-label="J${index + 1} ${names[index]}"><div class="range-limits"><span>${min.toFixed(1)}°</span><span>${max.toFixed(1)}°</span></div>`;
    $('#joint-controls').appendChild(row);
    const slider = row.querySelector('[type=range]');
    const number = row.querySelector('[type=number]');
    slider.addEventListener('input', () => session ? session.joint(index, radians(slider.valueAsNumber)) : state.setJoint(index, radians(slider.valueAsNumber)));
    // Commit the number field on Enter or blur, allowing incomplete negative/decimal input.
    number.addEventListener('blur', () => {
      if (session) session.joint(index, radians(number.valueAsNumber));
      else state.setJoint(index, radians(number.valueAsNumber));
      sync();
    });
    number.addEventListener('keydown', event => {
      if (event.key === 'Enter') number.blur();
    });
    return { slider, number, min, max };
  });

  function sync() {
    robot.apply(state);
    viewport.invalidate();
    rows.forEach(({ slider, number, min, max }, index) => {
      const value = degrees(state.positions[index]);
      slider.value = value;
      if (document.activeElement !== number) number.value = value.toFixed(1);
      setFill(slider, value, min, max);
    });
    $('#gripper-slider').value = state.gripper;
    setFill($('#gripper-slider'), state.gripper, 0, 100);
    $('#gripper-output').innerHTML = `${Math.round(state.gripper)}<span>%</span>`;
    $('#gripper-travel').textContent = `单指位移 ${(state.gripper / 100 * specification.gripperTravelMeters * 1000).toFixed(1)} mm`;
    document.querySelectorAll('[data-gripper]').forEach(button => button.classList.toggle('active', +button.dataset.gripper === state.gripper));
    const tip = robot.tipPosition();
    ['x', 'y', 'z'].forEach(axis => {
      const value = tip[axis] * 1000;
      $(`#tip-${axis}`).textContent = (Math.abs(value) < 0.05 ? 0 : value).toFixed(1);
    });
  }
  state.addEventListener('change', sync);
  $('#gripper-slider').addEventListener('input', event => session ? session.gripper(event.target.valueAsNumber) : state.setGripper(event.target.valueAsNumber));
  document.querySelectorAll('[data-gripper]').forEach(button => button.addEventListener('click', () => session ? session.gripper(+button.dataset.gripper) : state.setGripper(+button.dataset.gripper)));
  $('#home-pose').addEventListener('click', () => session ? session.home() : state.home());
  $('#vr-grab-pose').addEventListener('click', () => session?.preset('vr-grab'));
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
    viewport.setView(button.dataset.view);
    document.querySelectorAll('[data-view]').forEach(other => other.classList.toggle('active', other === button));
  }));
  $('#fit-view').addEventListener('click', () => viewport.fit());
  $('#grid-toggle').addEventListener('click', event => {
    viewport.grid.visible = !viewport.grid.visible;
    viewport.invalidate();
    event.currentTarget.setAttribute('aria-pressed', String(viewport.grid.visible));
  });
  $('#axes-toggle').addEventListener('click', event => {
    const show = event.currentTarget.getAttribute('aria-pressed') !== 'true';
    viewport.showAxes(show);
    event.currentTarget.setAttribute('aria-pressed', String(show));
  });
  sync();
  if (viewport.software) window.S1Startup.showDegraded(viewport.degradation);
  // Confirm the first frame succeeds before declaring the model ready.
  await during('RENDER_FRAME', '首帧渲染失败', () => {
    viewport.resize();
    viewport.renderer.render(viewport.scene, viewport.camera);
  });
  viewport.start();
  interactive.forEach(element => element.disabled = false);
  window.S1Startup.progress('正在准备工作台', '连接本地仿真环境…');
  $('#status-text').textContent = viewport.software ? '模型就绪 · Canvas 降级（性能和效果受限）' : '模型就绪 · WebGL';
  session = new Teleop({ state, robot, viewport });
  await session.connect();
  fetch('/api/client-status', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ browser: navigator.userAgent.includes('Chrome/') ? 'Chrome' : 'Other',
      renderer: viewport.software ? 'Canvas' : 'WebGL', status: 'ready' }),
  }).catch(error => console.warn('Local status report unavailable:', error.message));
  // Read-only diagnostics for browser QA; future robot backends can consume RobotState.
  window.s1Studio = Object.freeze({ snapshot: () => ({
    ...state.snapshot(), bodies: robot.bodyTransforms(),
    tipMeters: robot.tipPosition().toArray(), camera: viewport.camera.position.toArray(),
    cameraTarget: viewport.controls.target.toArray(),
    backend: session.snapshot,
  }) });
  window.S1Startup.progress('正在准备工作台', '整理工具栏与配置面板…');
  await installWorkbench({state, robot, viewport, session});
  session.hardware=new HardwareMouse(session);
  // Render at the final layout size before revealing the workbench.
  await new Promise(resolve => requestAnimationFrame(resolve));
  await during('RENDER_FRAME', '工作台首帧渲染失败', () => {
    viewport.resize();
    viewport.renderer.render(viewport.scene, viewport.camera);
  });
  await window.S1Startup.ready();
}
