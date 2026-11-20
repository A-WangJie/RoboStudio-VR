import {defaultArmConfig, validateArmConfig, readinessNotes, JOINT_LIMITS, SDK_REFERENCE} from './arm-config-model.js';
import {addTeachingPages, refreshTeachingPages} from './teaching-pages.js';
import {installHardwareDiagnostics} from './hardware-diagnostics.js';

export function createArmConfigPages() {
  const pages = new Map();
  let saved, storagePath = '', loading = true;
  const input = (path, label, options = {}) => {
    const {type = 'text', min, max, step = 'any', placeholder = '', suffix = ''} = options;
    return `<label class="arm-field"><span>${label}${suffix ? `<small>${suffix}</small>` : ''}</span><input data-arm-path="${path}" type="${type}" ${min !== undefined ? `min="${min}" max="${max}" step="${step}"` : ''} placeholder="${placeholder}" ${type === 'text' ? 'maxlength="253"' : ''}></label>`;
  };
  const select = (path, label, options) => `<label class="arm-field"><span>${label}</span><select data-arm-path="${path}">${options.map(([v,t]) => `<option value="${v}">${t}</option>`).join('')}</select></label>`;
  const check = (path, label) => `<label class="check-row"><input type="checkbox" data-arm-path="${path}">${label}</label>`;
  const unavailable = label => `<button type="button" disabled title="真机执行与关节状态服务尚未接入">${label}</button>`;
  const arms = builder => [0,1].map(i => `<fieldset class="arm-device" data-arm-index="${i}"><legend>机械臂 ${i ? 'B' : 'A'} <small>${i ? '第二设备槽位' : '第一设备槽位'}</small></legend>${builder(i, `arms.${i}`)}</fieldset>`).join('');
  function page(id, title, intro, html) {
    const root = document.createElement('div'); root.className = 'arm-config-page'; root.dataset.configPage = id;
    root.innerHTML = `<div class="arm-page-heading"><h2>${title}</h2><span class="arm-offline">离线配置</span></div><p class="arm-intro">${intro}</p>${html}
      <div class="arm-config-footer"><p class="arm-save-state" role="status">正在读取配置…</p><div class="arm-config-actions"><button type="button" data-arm-action="validate">校验配置</button><button type="button" data-arm-action="save" class="primary-button">保存配置</button></div><button type="button" data-arm-action="revert" class="arm-revert">撤销未保存修改</button><small class="arm-save-path"></small><ul class="arm-readiness"></ul></div>`;
    pages.set(id, {root, title}); return root;
  }
  page('arm-connection', '连接与设备识别', '检查实际 CAN 接口，再探测配置接口上的 S1 V1 节点。检测不会使能电机或执行运动。', `
    <div class="arm-detection" data-hardware-summary><strong data-hardware-title>实际连接：未检测</strong><span data-hardware-result>尚未探测机械臂</span><small data-hardware-time>检测结果不是持续在线或电机使能状态</small><button type="button" data-hardware-action="detect">检测机械臂</button></div>
    <div class="hardware-interface-list"><strong>电脑 CAN 接口</strong><div data-hardware-interfaces>正在读取接口…</div><button type="button" data-hardware-action="refresh">刷新接口</button></div>
    ${select('connection.layout','设备数量',[['auto','自动识别单臂 / 双臂'],['single','单臂 · 使用 A'],['dual','双臂 · 使用 A + B']])}
    <p class="arm-note">A、B 为独立执行臂，可作为 VR 遥控目标或实体主从示教的从臂。数量设置与“从臂示教模块”共用；接口名称不代表左右位置。</p>
    ${check('connection.autoDetect','打开真机配置页时自动检测已保存的设备')}
    ${input('connection.timeoutMs','连接超时',{type:'number',min:100,max:30000,step:100,suffix:'ms'})}
    <dl class="arm-spec"><div><dt>型号</dt><dd>S1 V1</dd></div><div><dt>通信</dt><dd>Linux SocketCAN</dd></div><div><dt>轴数</dt><dd>6 旋转关节 + 独立夹爪</dd></div></dl>
    <p class="arm-note">接口 UP 只表示电脑接口已启用。检测逐一查询已配置的 A / B 节点；自动模式按响应统计数量，不自动改变设备绑定。自动检测每次打开软件只执行一次；参数修改后请重新检测。</p>`);
  page('arm-devices', '机械臂参数', '分别设置 A、B 的 CAN 接口和末端类型。单臂模式只使用 A，B 的配置仍会保留。', '<button type="button" data-hardware-action="detect">检测当前设备配置</button><div class="arm-detection" data-hardware-feedback role="status" aria-live="polite"><strong data-hardware-feedback-title></strong><span data-hardware-feedback-result></span><small data-hardware-feedback-time></small></div>'+arms((i,p) => `
    ${input(`${p}.label`,'设备名称')}${input(`${p}.device`,'CAN 接口',{placeholder:`can${i}`})}<div class="hardware-arm-status" data-hardware-arm="${i}">未检测</div><button type="button" data-hardware-action="adopt" data-arm-slot="${i}">采用此接口实际速率</button>
    ${input(`${p}.bitrate`,'CAN 速率',{type:'number',min:10000,max:1000000,step:1,placeholder:'待硬件确认',suffix:'bit/s'})}
    ${select(`${p}.endEffector`,'末端类型',[['gripper','平行夹爪'],['None','无末端']])}
    ${check(`${p}.checkCollision`,'接入控制服务后启用 SDK 自碰撞检查（规划）')}
    <p class="arm-note">检测前核对所填速率与系统实际速率；留空仍可检测。采用速率只修改配置草稿，不改变系统 CAN 设置；需点击保存配置。</p>`)+`
    <details class="arm-reference"><summary>SDK 参数依据</summary><p>arm_version = V1；dev = 所填 CAN 接口；end_effector = gripper / None；check_collision = 自碰撞选项。</p><p>资料目录</p><code>${SDK_REFERENCE}</code><p>依据 readme.md、doc/S1_V1本地适配说明.md 与 S1_arm.py。</p></details>`);
  page('arm-startup', '初始化与复位', '读取所选真机的关节、夹爪与电机状态，再按需使能或失能。运动复位仍未接入。', `
    <details open class="arm-section"><summary>初始化检查</summary>${check('startup.readState','未来自动初始化时读取关节与夹爪（策略）')}${check('startup.checkLimits','未来自动初始化时核对实际关节限位（策略）')}<p class="arm-note">保存的初始化策略供后续自动流程使用；本页读取与使能均由按钮单独触发。</p><ol class="arm-steps"><li>检查 CAN 接口、速率与响应</li><li>识别机械臂，核对 A / B 设备绑定</li><li>读取实际姿态，核对限位和坐标</li><li>确认现场状态后单独使能</li></ol><div class="arm-operation-grid"><button type="button" data-hardware-action="detect">检查接口与响应</button><button type="button" data-hardware-action="read">读取状态</button><button type="button" data-hardware-action="enable" disabled>使能电机</button><button type="button" data-hardware-action="disable">失能电机</button></div></details>
    <div class="arm-detection" data-hardware-feedback role="status" aria-live="polite"><strong data-hardware-feedback-title></strong><span data-hardware-feedback-result></span><small data-hardware-feedback-time></small></div>
    <label class="arm-field"><span>真机操作目标</span><select data-hardware-target><option value="A">机械臂 A</option><option value="B">机械臂 B</option></select></label>
    <label class="check-row"><input type="checkbox" data-hardware-confirm>已确认目标机械臂及周围环境，允许电机输出力矩</label>
    <p class="arm-note">先读取完整状态，勾选确认后在 10 秒内使能。失能会撤去电机支撑，请先托稳机械臂。读数与使能状态均为本次反馈快照，不自动驱动仿真或启动遥控。关闭软件不会自动失能。</p>
    <p class="hardware-operation-message" data-hardware-operation-message role="status">尚未读取真机状态。</p>
    <div class="hardware-state" data-hardware-state></div>
    ${arms((i,p) => `<h3>复位目标 <small>关节角 / °</small></h3><div class="arm-joint-grid">${JOINT_LIMITS.map(([min,max],j) => input(`${p}.resetDegrees.${j}`,`J${j+1}`,{type:'number',min,max,step:.1,placeholder:'未设置',suffix:`${min}～${max}°`})).join('')}</div>${input(`${p}.resetSpeed`,'复位速度上限',{type:'number',min:.1,max:30,step:.1,suffix:'°/s · 工作台规划值'})}<p class="arm-note">六项留空表示尚无复位目标。填写的姿态需完成真机可达性与路径检查后才能使用。</p>`)}
    <div class="arm-operation-grid"><button type="button" data-hardware-action="preflight">复位参数检查</button>${unavailable('执行复位')}</div>
    <p class="hardware-preflight" data-hardware-preflight role="status">参数检查不执行复位，也不替代实际关节读取和路径校验。</p><details class="arm-reference"><summary>复位、零位与限位说明</summary><p>复位是运动到指定姿态；SDK 的 set_zero_position / set_end_zero_position 是写入零位，不能作为复位命令。当前页面不提供零位写入。</p><p>角度范围采用 SDK 文档与模型范围的保守交集。J3 文档为 170°，模型约 180°，当前取 170°；最终以实物确认数据为准。速度范围是工作台配置约束，不代表厂商额定速度。</p></details>`);
  page('xr-connection', 'VR 设备与连接', '设置头显与电脑的连接方式。当前为连接方案配置，位姿桥接服务尚未接入。', `
    <p class="arm-note">USB 实时采集已提供独立监视页：先运行 VR remote control/start-bridge.sh，再用 Google Chrome 打开 <strong>http://127.0.0.1:8767</strong>。此页连接配置暂不控制采集服务；监视页可启用本机 8765 工作台的 XYZ 运动学仿真跟随。</p>
    <div class="arm-detection"><strong>VR 数据会话：未接入</strong><span>头显：未检测　／　左右手柄：未检测</span><small>追踪有效性、数据帧率和延迟：暂无数据</small></div>
    ${select('ar.connection.device','设备类型',[['quest','Meta Quest / Touch 手柄'],['openxr','其他 OpenXR 头显（待适配）']])}
    ${select('ar.connection.transport','连接方案',[['wifi','局域网 · Wi-Fi'],['usb','USB · 调试与转发']])}
    ${input('ar.connection.host','电脑桥接主机',{placeholder:'例如 192.168.1.100'})}
    ${input('ar.connection.port','桥接端口',{type:'number',min:1024,max:65535,step:1,suffix:'规划值'})}
    ${input('ar.connection.serial','头显序列号（可选）',{placeholder:'用于区分多台设备'})}
    ${check('ar.connection.autoReconnect','服务接入后尝试恢复数据连接')}
    <p class="arm-note">以上参数仅保存。端口 8766 为预留值，尚无服务监听；主机留空时表示连接目标待配置。重连后仍需重新对齐和按住使能。</p>
    <div class="arm-operation-grid">${unavailable('检测 VR 设备')}${unavailable('连接位姿会话')}${unavailable('断开会话')}</div>
    <details open class="arm-section"><summary>USB 与 Wi-Fi 的区别</summary><p class="arm-note">USB / ADB 用于授权、安装头显程序或建立端口转发。ADB 显示设备在线，不等于手柄位姿已经接入。</p><p class="arm-note">Wi-Fi 方案要求头显与电脑网络可达，头显端运行位姿采集程序，并连接电脑桥接服务。USB 转发的地址和端口需与实际转发规则一致。</p></details>`);
  page('xr-guide', '使用流程与状态说明', '按设备连接、输入验证、坐标对齐、仿真跟随的顺序准备遥操作。当前仅完成配置界面。', `
    <details open class="arm-section"><summary>1. 头显与手柄准备</summary><p class="arm-note">完成头显边界与手柄配对，确认左右手柄追踪正常。Quest 使用 USB 调试时，需要开发者模式并在头显内接受电脑授权。</p></details>
    <details open class="arm-section"><summary>2. 建立位姿数据连接</summary><p class="arm-note">头显端采集程序通过 OpenXR 读取手柄位置、旋转、按键及追踪状态，再通过位姿桥接服务传给工作台。当前采集程序与桥接服务尚未实现。</p></details>
    <details open class="arm-section"><summary>3. 分配输入与坐标对齐</summary><p class="arm-note">在“输入配对与坐标”中将左右手分别分配给机械臂 A / B。两台均为独立执行臂。核对基座与 TCP，记录手柄起点和机械臂起点后使用相对运动映射；仅填写零偏移不表示标定完成。</p></details>
    <details open class="arm-section"><summary>4. 先验证仿真跟随</summary><p class="arm-note">先检查 XYZ 方向和位移比例，再检查旋转及夹爪。按住使能才发送目标；松开、追踪丢失或数据超时后停止更新目标。具体按键映射待头显端程序确定。</p></details>
    <dl class="arm-spec"><div><dt>设备在线</dt><dd>仅表示通信可达</dd></div><div><dt>位姿有效</dt><dd>新鲜且追踪有效的数据</dd></div><div><dt>配对完成</dt><dd>输入已绑定目标机械臂</dd></div><div><dt>允许跟随</dt><dd>对齐完成并按住使能</dd></div></dl>
    <div class="arm-operation-grid">${unavailable('记录对齐起点')}${unavailable('开始仿真跟随')}</div><p class="arm-note">硬件连接、实时状态与跟随功能将在接入服务后开放。保存配置不会启动设备扫描或机械臂运动。</p>`);
  page('arm-ar', '输入配对与坐标', '预留两个执行臂的输入分配及坐标参数。当前未连接 AR 设备，保存后不会启动跟随。', `
    <div class="arm-detection"><strong>AR 会话：未接入</strong><span>配对状态：待配置与标定</span></div>
    ${arms((i,p) => `${select(`${p}.arSource`,'控制输入',[['unassigned','暂不分配'],['left','AR 左手输入'],['right','AR 右手输入']])}${input(`${p}.positionScale`,'位移比例',{type:'number',min:.05,max:2,step:.05,suffix:'手部位移 × 比例'})}<details class="arm-section"><summary>基座与 TCP 偏移</summary><p class="arm-note">基座位姿：机械臂基座相对于共同工作坐标系；XYZ 为 mm，Roll / Pitch / Yaw 为 °。</p><div class="arm-joint-grid">${['X','Y','Z','Roll','Pitch','Yaw'].map((label,j)=>input(`${p}.basePose.${j}`,label,{type:'number',min:j<3?-10000:-180,max:j<3?10000:180,step:.1})).join('')}</div><p class="arm-note">TCP 偏移：工具点相对于末端法兰坐标系，单位 mm。</p><div class="arm-joint-grid">${['X','Y','Z'].map((label,j)=>input(`${p}.tcpOffset.${j}`,label,{type:'number',min:-1000,max:1000,step:.1})).join('')}</div>${check(`${p}.calibrationConfirmed`,'已在外部完成并核对坐标标定')}<p class="arm-note">零值仅为占位，勾选是人工记录，不代表软件已验证标定。</p></details>`)}
    <label class="check-row"><input type="checkbox" checked disabled>按住使能后才允许跟随</label>${input('ar.timeoutMs','输入丢失超时',{type:'number',min:100,max:5000,step:50,suffix:'ms'})}<p class="arm-note">超时后停止接收新的跟随目标；具体制动行为由后续真机控制模块实现。以上参数尚未作用于机器人。</p>`);
  pages.get('xr-guide').root.querySelector('.arm-config-footer').remove();
  pages.get('xr-guide').root.querySelector('.arm-offline').textContent = '使用说明';
  for (const [id, label] of [['arm-connection','连接检测'],['arm-devices','设备参数'],['arm-startup','真机状态 / 使能']]) {
    pages.get(id).root.querySelector('.arm-offline').textContent = label;
  }
  addTeachingPages({page, input, select, check, unavailable});
  const roots = [...pages.values()].map(p=>p.root).filter(root=>root.querySelector('.arm-config-footer'));
  const fields = () => roots.flatMap(r=>[...r.querySelectorAll('[data-arm-path]')]);
  function setStatus(text, error=false) {roots.forEach(r=>{const e=r.querySelector('.arm-save-state'); e.textContent=text; e.classList.toggle('error',error);});}
  function syncLayout() {
    const single = fields().find(f=>f.dataset.armPath==='connection.layout').value==='single';
    roots.forEach(r=>r.querySelectorAll('[data-arm-index="1"], [data-teaching-index="1"]').forEach(e=>{e.disabled=single; e.classList.toggle('arm-inactive',single);}));
  }
  function fill(config) {
    for(const f of fields()) {
      const value=f.dataset.armPath.split('.').reduce((v,key)=>v?.[key],config);
      if(f.type==='checkbox') f.checked=!!value; else f.value=value??'';
    }
    syncLayout();
    refreshTeachingPages(roots, config);
  }
  function collect() {
    const config=defaultArmConfig();
    config.arms.forEach(a=>a.resetDegrees=[]);
    for(const f of fields()) {
      const keys=f.dataset.armPath.split('.'), last=keys.pop();
      const parent=keys.reduce((v,key)=>v[key],config);
      parent[last]=f.type==='checkbox'?f.checked:f.type==='number'?(f.value===''?null:f.valueAsNumber):f.hasAttribute('data-arm-number')?Number(f.value):f.value.trim();
    }
    config.arms.forEach(a=>{if(a.resetDegrees.every(v=>v===null)) a.resetDegrees=null;});
    return validateArmConfig(config);
  }
  function notes(config) {
    roots.forEach(r=>{const list=r.querySelector('.arm-readiness'); list.replaceChildren();
      const teaching = r.dataset.configPage === 'arm-teaching' || r.dataset.configPage.startsWith('teaching-');
      for(const note of readinessNotes(config, teaching ? 'teaching' : 'all')) {const li=document.createElement('li');li.textContent=note;list.append(li);}
    });
  }
  for(const root of roots) {
    const changed = event => {
      if (loading) return;
      const field = event.target.closest('[data-arm-path]');
      if (field) {
        // Repeated fields are views of one draft, never independent copies.
        for (const peer of fields().filter(f=>f!==field && f.dataset.armPath===field.dataset.armPath)) {
          if (field.type==='checkbox') peer.checked=field.checked; else peer.value=field.value;
        }
        setStatus('有未保存修改');
        roots.forEach(r=>r.querySelector('.arm-readiness').replaceChildren());
        syncLayout();
      }
      try {refreshTeachingPages(roots, collect());}
      catch(error) {roots.forEach(r=>r.querySelectorAll('[data-teaching-output]').forEach(e=>{e.textContent='请先校验配置：'+error.message;e.classList.add('error');}));}
    };
    root.addEventListener('input', changed);
    root.addEventListener('change', changed);
    root.addEventListener('click',async event=>{
      const action=event.target.closest('[data-arm-action]')?.dataset.armAction;
      if(!action || loading) return;
      if(action==='revert'){fill(saved);notes(saved);setStatus('已恢复上次保存的配置');return;}
      try {
        const config=collect();notes(config);
        if(action==='validate'){setStatus('配置格式校验通过；连接状态以最近检测结果为准。');return;}
        setBusy(true); setStatus('正在保存配置…');
        if(window.s1Desktop?.saveArmConfig) {
          const result=await window.s1Desktop.saveArmConfig(config); saved=result.config; storagePath=result.path;
        } else {localStorage.setItem('robostudio.arm-config.v1',JSON.stringify(config));saved=config;}
        fill(saved);notes(saved);setStatus('配置已保存；保存本身不发送探测或运动命令。');
      } catch(error) {setStatus(error.message,true);}
      finally {setBusy(false);}
    });
  }
  function setBusy(busy) {loading=busy; roots.forEach(r=>r.querySelectorAll('[data-arm-action], [data-arm-path]').forEach(b=>b.disabled=busy));syncLayout();roots[0].dispatchEvent(new Event('arm-config-updated'));}
  setBusy(true);
  pages.ready = (async()=>{
    try {
      if(window.s1Desktop) {
        if(!window.s1Desktop.armConfig) throw new Error('请重启桌面软件以启用机械臂配置存储');
        const result=await window.s1Desktop.armConfig();saved=result.config;storagePath=result.path;pages.hasSavedConfig=result.exists===true;
      } else {const raw=localStorage.getItem('robostudio.arm-config.v1');pages.hasSavedConfig=!!raw; saved=raw?validateArmConfig(JSON.parse(raw)):defaultArmConfig();storagePath='当前浏览器本地配置';}
      fill(saved);notes(saved);roots.forEach(r=>r.querySelector('.arm-save-path').textContent=`保存位置：${storagePath}`);
      setBusy(false);setStatus('配置已读取 · 可检查接口与机械臂响应');roots.forEach(r=>r.dataset.ready='true');
    } catch(error) {setStatus(`读取失败：${error.message}`,true);}
  })();
  installHardwareDiagnostics({pages, roots, collect, fields, isReady:()=>!loading, setStatus});
  return pages;
}
