import {JOINT_LIMITS} from './arm-config-model.js';
import {mapTeachingJoints} from './teaching-model.js';

export function addTeachingPages({page, input, select, check, unavailable}) {
  const layout = () => select('connection.layout', '从臂数量 · 与机械臂配置共用', [
    ['auto','自动识别单臂 / 双臂'], ['single','单臂 · 一组主从（A）'], ['dual','双臂 · 两组主从（A + B）']]);
  const channels = builder => ['A','B'].map((id,i) => `<fieldset class="arm-device" data-teaching-index="${i}"><legend>通道 ${id}<small>主臂 ${id} → 从臂 ${id}</small></legend>${builder(i, `teaching.pairs.${i}`)}</fieldset>`).join('');
  page('arm-teaching', '主从示教配置', '配置实体主臂与从臂的设备配对。这里与“从臂示教模块”共用配置，修改后保存一次即可。', `
    ${layout()}<p class="arm-note">A、B 为从臂槽位。单臂使用一台主臂和一台从臂；双臂使用两组主从。单臂模式保留 B 组参数。</p>
    ${channels((i,p) => `${check(`${p}.enabled`,'此通道参与示教')}
      <dl class="arm-spec"><div><dt>目标从臂</dt><dd data-teaching-follower="${i}">读取配置中…</dd></div></dl>
      ${input(`${p}.leader.label`,'主臂名称')}${input(`${p}.leader.device`,'主臂 CAN 接口',{placeholder:`can${i+2}`})}
      ${input(`${p}.leader.bitrate`,'主臂 CAN 速率',{type:'number',min:10000,max:1000000,step:1,placeholder:'待硬件确认',suffix:'bit/s'})}`)}
    <p class="arm-note">从臂接口沿用“机械臂参数”；主臂接口须与所有参与的主臂、从臂分开。此处填写接口名，不会修改系统 CAN 设置。</p>
    <div class="arm-operation-grid"><button type="button" data-open-function="arm-devices">查看从臂参数</button><button type="button" data-open-function="teaching-mapping">关节映射设置</button></div>`);

  page('teaching-session', '单 / 双臂主从示教', '选择参与示教的从臂数量，检查主从配对，再准备开始示教。', `
    <div class="arm-detection"><strong>示教状态：未启动</strong><span>实体主臂读取：在数据采集页启动</span><span>从臂 A / B：未检测</span><small>已提供配置与离线映射预览；实体主臂只读采集请进入“数据采集”选择示教臂来源；此页尚不支持下发示教运动。</small></div>
    ${layout()}
    <div class="teaching-channel-summary"><p data-teaching-summary="0"></p><p data-teaching-summary="1"></p></div>
    <div class="arm-operation-grid">${unavailable('开启单臂示教')}${unavailable('开启双臂示教')}${unavailable('停止示教')}</div>
    <p class="arm-note">开启条件：主从设备在线、接口与速率已核对、起始姿态已对齐。真机服务接入后开放启动按钮；配置数量不代表设备已在线。</p>
    <details open class="arm-section"><summary>跟随参数</summary>
      ${input('teaching.rateHz','目标更新频率',{type:'number',min:1,max:100,step:1,suffix:'Hz · 配置值'})}
      ${input('teaching.timeoutMs','主臂数据超时',{type:'number',min:100,max:5000,step:1,suffix:'ms'})}
      ${check('teaching.gripper','跟随主臂夹爪开合')}
      <label class="check-row"><input type="checkbox" checked disabled>按住使能才允许跟随</label>
    </details>
    <div class="arm-operation-grid"><button type="button" data-open-function="arm-teaching">主从配对配置</button><button type="button" data-open-function="teaching-mapping">映射与角度预览</button></div>`);

  page('teaching-mapping', '关节映射与对齐', '按六关节配置主从映射，核对方向、比例与偏移。主从设备需具有相容的关节结构。', `
    <p class="teaching-formula">从臂目标角 = 主臂角 × 方向 × 比例 + 偏移</p>
    ${channels((i,p) => `<div class="teaching-mapping-grid"><span>关节</span><span>方向</span><span>比例</span><span>偏移 / °</span>
      ${JOINT_LIMITS.map((_,j) => `<strong>J${j+1}</strong>
        <select data-arm-path="${p}.direction.${j}" data-arm-number aria-label="通道 ${i?'B':'A'} J${j+1} 方向"><option value="1">同向</option><option value="-1">反向</option></select>
        <input data-arm-path="${p}.scale.${j}" type="number" min="0.1" max="2" step="0.05" aria-label="通道 ${i?'B':'A'} J${j+1} 比例">
        <input data-arm-path="${p}.offsetDegrees.${j}" type="number" min="-180" max="180" step="0.1" aria-label="通道 ${i?'B':'A'} J${j+1} 偏移">`).join('')}</div>
      ${check(`${p}.alignmentConfirmed`,'已在现场核对主从起始姿态与关节方向')}
      <details class="arm-section"><summary>离线角度预览</summary><p class="arm-note">输入主臂角度，仅计算从臂目标与限位结果，不会移动机械臂。</p>
        <div class="arm-joint-grid">${JOINT_LIMITS.map((_,j)=>`<label class="arm-field"><span>主臂 J${j+1}<small>°</small></span><input type="number" value="0" min="-360" max="360" step="0.1" data-teaching-preview="${i}" data-joint="${j}"></label>`).join('')}</div>
        <output class="teaching-preview-result" data-teaching-output="${i}" role="status">等待配置</output>
      </details>`)}
    <p class="arm-note">零偏移只是默认值，勾选核对不表示软件已验证标定。预览超限会明确标出，不会静默截断目标角。</p>`);

  const guide = page('teaching-guide', '示教操作说明', '实体主臂提供关节读数，从臂按配对和映射跟随。', `
    <ol class="arm-steps"><li>在“机械臂配置”中填写从臂 A / B 的接口、速率及末端。</li><li>选择单臂或双臂，在“主从示教配置”中填写对应主臂接口。</li><li>在“关节映射与对齐”中核对方向和比例，使用离线角度预览检查限位。</li><li>现场对齐主从起始姿态，保存配置。</li><li>接入实体主臂与从臂服务后，读取实际状态，再人工确认开启示教。</li><li>数据过期、设备断开或松开使能时停止跟随；重新开始前再次核对姿态。</li></ol>
    <div class="arm-detection"><strong>当前阶段：配置与离线预览</strong><small>数据采集页已接入实体主臂 SDK 只读关节采集。单 / 双从臂运动与重力补偿尚未接入；主臂原始关节角与 VR 数据分开标记，离线预览不会作为真机读数。</small></div>`);
  guide.querySelector('.arm-config-footer').remove();
  guide.querySelector('.arm-offline').textContent = '使用说明';
}

export function refreshTeachingPages(roots, config) {
  for (const root of roots) {
    root.querySelectorAll('[data-teaching-follower]').forEach(element => {
      const arm = config.arms[Number(element.dataset.teachingFollower)];
      element.textContent = `${arm.label} · ${arm.device}`;
    });
    root.querySelectorAll('[data-teaching-summary]').forEach(element => {
      const i = Number(element.dataset.teachingSummary), pair = config.teaching.pairs[i], arm = config.arms[i];
      const active = pair.enabled && (i === 0 || config.connection.layout !== 'single');
      element.textContent = `${active?'参与':'停用'}：${pair.leader.label} (${pair.leader.device||'接口未设置'}) → ${arm.label} (${arm.device})`;
      element.classList.toggle('teaching-muted', !active);
    });
    root.querySelectorAll('[data-teaching-output]').forEach(element => {
      const i = Number(element.dataset.teachingOutput);
      try {
        const angles = [...root.querySelectorAll(`[data-teaching-preview="${i}"]`)].map(f => f.value === '' ? NaN : f.valueAsNumber);
        const {target, violations} = mapTeachingJoints(config.teaching.pairs[i], angles, JOINT_LIMITS);
        element.textContent = `从臂目标 / °：${target.map(v=>v.toFixed(1)).join(' / ')}\n${violations.length?'超出限位：'+violations.join('、'):'六轴目标在配置限位内 · 未执行运动'}`;
        element.classList.toggle('error', !!violations.length);
      } catch(error) {element.textContent=error.message;element.classList.add('error');}
    });
  }
}
