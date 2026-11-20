import {installHardwareOperations} from './hardware-operations.js';
// Automatic work is restricted to interface inventory and optional ping detection.
export function installHardwareDiagnostics({pages, roots, collect, fields, isReady, setStatus}) {
  const connection = pages.get('arm-connection').root;
  const devices = pages.get('arm-devices').root;
  const startup = pages.get('arm-startup').root;
  const views = [connection, devices, startup];
  const title = connection.querySelector('[data-hardware-title]');
  const summary = connection.querySelector('[data-hardware-result]');
  const timing = connection.querySelector('[data-hardware-time]');
  const list = connection.querySelector('[data-hardware-interfaces]');
  let interfaces = [], latest = null, busy = false, refreshBusy = false, error = '', inventoryError = '', autoPending = false, refreshAt = 0;
  let preflightConfig = '';
  const selection = config => ({layout:config.connection.layout, timeoutMs:config.connection.timeoutMs,
    arms:config.arms.map(({id, device, bitrate, endEffector})=>({id, device, bitrate, endEffector}))});
  const current = () => selection(collect());
  const operations=installHardwareOperations({startup,current,isReady,setStatus,detectionBusy:()=>busy});
  const interfaceChanged = () => latest?.arms.some(arm => {
    if(arm.status==='unused')return false;
    const info=interfaces.find(i=>i.device===arm.device), before=arm.interface;
    return JSON.stringify(info ? [info.up,info.busState,info.bitrate] : null)!==JSON.stringify(before ? [before.up,before.busState,before.bitrate] : null);
  });
  const matches = () => {try {return latest && !inventoryError && !interfaceChanged() && JSON.stringify(latest.config)===JSON.stringify(current());}catch {return false;}};
  const labels = {online:'响应正常', partial:'部分节点未响应', no_response:'未收到响应', missing_interface:'接口不存在',
    interface_down:'接口未启动', bus_fault:'总线异常', bitrate_mismatch:'速率不一致', probe_error:'探测失败', unused:'未启用'};
  const visible = () => views.some(root => root.isConnected && !root.closest('.function-page')?.hidden && !document.body.classList.contains('hide-control-panel'));
  function controls() {
    for (const root of views) for (const button of root.querySelectorAll('[data-hardware-action]')) {
      button.disabled = busy || operations.isBusy() || !isReady() || (button.dataset.hardwareAction==='refresh' && refreshBusy);
    }
    operations.render();
  }
  function render() {
    controls();
    if(preflightConfig) {
      let same=false;try {same=preflightConfig===JSON.stringify(collect());}catch {}
      if(!same){startup.querySelector('[data-hardware-preflight]').textContent='参数已更改，请重新检查复位参数。';preflightConfig='';}
    }
    const matching = matches(), age = latest ? Math.max(0, (Date.now()-latest.checkedAtMs)/1000) : 0;
    const historical = age>10;
    title.textContent = busy?'正在检测机械臂…':error?'检测未完成':!latest?'实际连接：未检测':inventoryError?'接口状态读取失败':interfaceChanged()?'接口状态已改变，请重新检测':!matching?'配置已更改，请重新检测':
      `${historical?'历史':'最近'}检测：${latest.detectedCount} 台响应正常`;
    title.classList.toggle('hardware-ok', !!matching && !historical && latest.detectedCount>0 && !busy && !error);
    summary.textContent = busy?'正在查询配置接口的关节与末端节点，请稍候…':error || (matching ? latest.arms.map(a=>`${a.id} · ${a.device}：${labels[a.status]||a.status}`+
      (a.requiredNodes?`（${a.respondingNodes.length}/${a.requiredNodes.length} 节点响应）`:'')+
      (a.status!=='online' && a.status!=='unused'?`，${a.message}`:'')).join('；') :
      latest?'上次结果不能用于当前配置或接口状态':'点击“检测机械臂”查询所配置接口');
    timing.textContent = latest ? `检测于 ${new Date(latest.checkedAtMs).toLocaleTimeString()} · ${Math.floor(age)} 秒前；${historical?'结果已过期，需重新检测。':''}不是持续在线或使能状态` : '仅查询节点响应，不使能电机，不读取实际关节角。';
    for(const root of views) for(const feedback of root.querySelectorAll('[data-hardware-feedback]')) {
      const heading=feedback.querySelector('[data-hardware-feedback-title]');
      if(heading.textContent!==title.textContent)heading.textContent=title.textContent;
      heading.classList.toggle('hardware-ok',title.classList.contains('hardware-ok'));
      const detail=feedback.querySelector('[data-hardware-feedback-result]');
      if(detail.textContent!==summary.textContent)detail.textContent=summary.textContent;
      // Keep elapsed seconds outside the live announcement to avoid repeated speech.
      const time=feedback.querySelector('[data-hardware-feedback-time]');
      time.setAttribute('aria-live','off');time.textContent=timing.textContent;
    }
    for (const element of devices.querySelectorAll('[data-hardware-arm]')) {
      const row = matching && latest.arms[Number(element.dataset.hardwareArm)];
      element.classList.toggle('hardware-ok',!!row && row.status==='online' && !historical && !error);
      element.textContent = !row?'未检测当前配置':`${historical?'历史检测 · ':''}${labels[row.status]||row.status} · ${row.message}`+
        (row.respondingNodes?.length?`\n响应节点：${row.respondingNodes.join(' / ')}；${row.respondingNodes.length} / ${row.requiredNodes.length}`:'');
    }
    list.replaceChildren();
    if(inventoryError){list.textContent=inventoryError;return;}
    if (!interfaces.length) {list.textContent='未发现 CAN 接口，或接口信息尚未读取';return;}
    for (const info of interfaces) {
      const item=document.createElement('div'); item.className='hardware-interface';
      const name=document.createElement('strong');name.textContent=`${info.device} · ${info.up?'UP':'DOWN'}`;
      const detail=document.createElement('small');detail.textContent=`${info.bitrate??'未知'} bit/s · ${info.busState}\n接收 ${info.rxPackets} / 发送 ${info.txPackets} · 错误 ${info.rxErrors+info.txErrors}`;
      item.append(name,detail);list.append(item);
    }
  }
  async function call(path, body) {
    const response=await fetch('/api/hardware/'+path, {method:body?'POST':'GET',
      headers:{'Content-Type':'application/json'}, ...(body?{body:JSON.stringify(body)}:{}),
      signal:AbortSignal.timeout(body?body.timeoutMs*2+8000:5000)});
    let result;try {result=await response.json();}catch {throw Error('真机检测服务不可用，请完整重启 RS');}
    if(!response.ok)throw Error(result.message||'真机检测服务不可用');
    return result;
  }
  async function refresh() {
    if(refreshBusy||busy||operations.isBusy())return;
    refreshBusy=true;controls();
    try {interfaces=(await call('interfaces')).interfaces;inventoryError='';}
    catch(e) {inventoryError=e.message;}
    finally {refreshBusy=false;render();}
  }
  async function detect() {
    if(busy||operations.isBusy()||!isReady())return;
    let config;try {config=current();}catch(e){latest=null;error=e.message;setStatus(e.message,true);render();return;}
    busy=true;error='';latest=null;render();
    try {
      latest=await call('detect',config);interfaces=latest.interfaces;inventoryError='';
      setStatus('节点检测完成；结果未保存为设备参数，也不表示允许真机运动。');
    }catch(e){error=e.message;setStatus(e.message,true);}
    finally {busy=false;render();}
  }
  function adopt(slot) {
    const config=current(), arm=config.arms[slot], info=interfaces.find(i=>i.device===arm.device);
    if(!info?.bitrate)throw Error('该接口没有可读取的实际速率，请先刷新接口');
    const field=fields().find(f=>f.dataset.armPath===`arms.${slot}.bitrate`);
    field.value=info.bitrate;field.dispatchEvent(new Event('input',{bubbles:true}));
    setStatus(`已填入 ${arm.device} 实际速率 ${info.bitrate} bit/s；请保存配置。`);render();
  }
  function preflight() {
    const config=collect(), selected=config.connection.layout==='single'?config.arms.slice(0,1):config.arms;
    const checks=[];
    for(const arm of selected) {
      const result=matches() && latest.arms.find(a=>a.id===arm.id);
      checks.push(`${arm.id} · ${arm.device}：${result?.status==='online' && Date.now()-latest.checkedAtMs<=10000?'近期节点响应通过':'需要重新检测节点'}`);
      checks.push(arm.resetDegrees?`复位目标 ${arm.resetDegrees.join(' / ')} °，参数在配置限位内`:'复位目标：尚未设置六轴角度');
      checks.push(`规划速度上限：${arm.resetSpeed} °/s`);
    }
    checks.push(`参数检查时间：${new Date().toLocaleTimeString()}。实际关节读取、实际起点限位及路径检查尚未接入；此结果不开放运动或写入零位。`);
    startup.querySelector('[data-hardware-preflight]').textContent=checks.join('\n');
    preflightConfig=JSON.stringify(config);
  }
  for (const root of views) root.addEventListener('click',event=>{
    const button=event.target.closest('[data-hardware-action]');if(!button||button.disabled)return;
    const action=button.dataset.hardwareAction;
    if(action==='detect')void detect();
    else if(action==='refresh')void refresh();
    else if(['read','enable','disable'].includes(action))void operations.operate(action);
    else try {if(action==='adopt')adopt(Number(button.dataset.armSlot));else preflight();}catch(e){setStatus(e.message,true);}
  });
  for(const root of roots) {
    root.addEventListener('arm-config-updated',render);
    root.addEventListener('input',()=>render());root.addEventListener('change',()=>render());
    // save/revert also changes the selection without an input event.
    root.addEventListener('click',()=>queueMicrotask(render));
  }
  pages.ready.then(()=>{
    let stored=!!window.s1Desktop;
    if(!window.s1Desktop)try {stored=!!localStorage.getItem('robostudio.arm-config.v1');}catch {stored=false;}
    // Only auto-probe when a saved config was present at startup. Saving never sends frames.
    autoPending=stored && pages.hasSavedConfig===true && collect().connection.autoDetect;
    render();
  }).catch(()=>{});
  const timer=setInterval(()=>{
    if(!visible()||!isReady())return;
    if(autoPending){autoPending=false;void detect();}
    else if(Date.now()>=refreshAt){refreshAt=Date.now()+3000;void refresh();}
    else render();
  },1000);
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  render();
}
