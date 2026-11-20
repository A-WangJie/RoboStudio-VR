// VR-specific view and heartbeat; shared motion authority remains in RS.
export function installVRHardware(control) {
 const $=s=>control.querySelector(s);
 const block=document.createElement('fieldset');block.className='vr-hardware-settings';
 block.innerHTML=`<legend>控制对象</legend><label>运行目标<select id="vr-execution"><option value="simulation">仿真机械臂</option><option value="hardware">实体机械臂 · S1 V1</option></select></label>
 <div id="vr-hardware-options" hidden><label>目标机械臂<select id="vr-hardware-arm"><option value="A">机械臂 A</option><option value="B">机械臂 B</option></select></label>
 <label>关节速度上限 / °/s<input id="vr-hardware-speed" type="number" min="0.5" max="10" step="0.5" value="3"></label>
 <button id="vr-hardware-use-limit" type="button">采用当前允许上限 · 10°/s</button>
 <small>保留已保存的速度；点击上方按钮才应用 10°/s。此值是当前软件上限，不代表电机性能极限。</small>
 <label>跟随解算<select id="vr-hardware-solver"><option value="pose">完整位姿 · 与仿真一致</option><option value="position">仅跟随位置 · 腕部自适应</option></select></label>
 <small>仅位置模式不保持工具朝向，适合分辨位移跟随是否受到姿态约束；完整位姿模式沿用手柄姿态开关。</small>
 <details><summary>夹爪行程 · 实际电机角度</summary><label>闭合角度 / °<input id="vr-hardware-closed" type="number" min="-170" max="170" step="0.1" placeholder="未标定"></label><label>张开角度 / °<input id="vr-hardware-open" type="number" min="-170" max="170" step="0.1" placeholder="未标定"></label><small>两项留空则不接管真机夹爪；扳机开关需关闭。可沿用鼠标控制已核对的行程。</small></details>
 <label><input id="vr-hardware-confirm" type="checkbox">已核对零位、方向、工具及现场，允许限速移动到抓取位姿</label>
 <button id="vr-hardware-stop">停止真机 VR</button><p id="vr-hardware-status" role="status">真机控制未开启</p>
 <small>先使能电机。进入后限速移至抓取位姿；A 启动／重置跟随，B 复位。按住右握键运动，松开保持。退出先停止跟随，再按所选速度回到六轴零位；停止真机 VR 则立即保持当前位置。均不自动失能。末端使用模型 TCP；软件停止不代替硬件急停。</small></div>`;
 control.querySelector('.vr-session').after(block);
 let state={selected:false,active:false},settings=null,token=null,busy=false,stopping=false,mode='simulation',last='',cancelStart=false;
 const message=(text,error=false)=>{$('#vr-hardware-status').textContent=text;$('#vr-hardware-status').classList.toggle('vr-hardware-error',error);};
 const configFields=['vr-hardware-arm','vr-hardware-speed','vr-hardware-solver','vr-hardware-closed','vr-hardware-open'];
 try {
  const own=JSON.parse(localStorage.getItem('robostudio.vr-hardware.v1')||'null');
  const mouse=JSON.parse(localStorage.getItem('robostudio.mouse-hardware.v1')||'null');
  if(own){for(const id of configFields)if(own[id]!==undefined)$('#'+id).value=own[id];}
  else if(mouse){for(const [id,key] of [['vr-hardware-arm','#mouse-hardware-arm'],['vr-hardware-speed','#mouse-hardware-speed'],['vr-hardware-closed','#mouse-gripper-closed'],['vr-hardware-open','#mouse-gripper-open']])if(mouse[key]!==undefined)$('#'+id).value=mouse[key];}
 }catch{}
 async function request(action,body) {
  const r=await fetch('/api/hardware/vr/'+action,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(1800)});
  const result=await r.json();if(!r.ok)throw Error(result.message||'真机 VR 请求失败');return result;
 }
 function render() {
  $('#vr-execution').disabled=busy||state.active;$('#vr-execution').value=mode;
  $('#vr-hardware-options').hidden=mode!=='hardware';
  for(const id of configFields)$('#'+id).disabled=busy||state.active;
  if(settings){$('#vr-hardware-arm').options[1].disabled=settings.config.layout==='single';if(settings.config.layout==='single')$('#vr-hardware-arm').value='A';}
  $('#vr-hardware-confirm').disabled=busy||state.active;
  $('#vr-hardware-use-limit').disabled=busy||state.active;
  $('#vr-hardware-stop').disabled=busy||!state.active;
  if(mode!=='hardware')return;
  for(const id of ['vr-gain','vr-rotation','vr-gripper'])$('#'+id).disabled=busy||state.active;
  const buttons=Object.fromEntries([...control.querySelectorAll('[data-action]')].map(b=>[b.dataset.action,b]));
  buttons['vr/enter'].textContent='进入 VR 模式';buttons['vr/exit'].textContent='退出 VR 模式（回零）';
  buttons['vr/enter'].disabled=busy||state.active||!settings||!$('#vr-hardware-confirm').checked;
  buttons['vr/reset'].disabled=busy||!state.active||state.uiPaused||state.preparing;buttons['vr/exit'].disabled=busy||!state.active||state.phase==='returning-zero';
  buttons['simulation/enable'].disabled=busy||!state.active||state.preparing||state.uiPaused;
  buttons['simulation/disable'].disabled=busy||!state.active;
  $('[data-v="mode"]').textContent=state.uiPaused?'真机 VR 已暂停 · 会话保留':state.preparing?(state.phase==='returning-zero'?'真机正在限速回零，完成后退出 VR…':'真机正按限速移动到抓取位姿…'):state.active?'真机 VR 模式 · '+(state.armId||'A'):'真机 VR 未开启';
  const tracking=state.tracking;
  $('[data-v="follow"]').textContent=(state.message||'真机 VR 未开启')+` · 已接受 ${state.sent||0} 个目标`+(tracking?` · 末端偏差 ${tracking.positionErrorMm} mm · 目标前置 ${tracking.targetLeadMm} mm · 逆解步长 ${Math.round(tracking.ikStepFraction*100)}% · 速度上限 ${tracking.speedDegS.toFixed(1)}°/s`:'');
 }
 async function stop(reason='真机 VR 已停止，保持当前位置') {
  if(stopping)return;stopping=true;cancelStart=true;token=null;
  try{state=await request('stop',{});message(reason);}catch(e){message('停止回执未收到，请检查真机状态。'+e.message,true);}
  finally{stopping=false;$('#vr-hardware-confirm').checked=false;render();}
 }
 async function action(path) {
  busy=true;cancelStart=false;render();
  try {
   if(path==='vr/enter') {
    if(!$('#vr-hardware-confirm').checked)throw Error('请先完成真机现场确认');
    const r=await fetch('/api/hardware/mouse/settings');settings=await r.json();if(!r.ok)throw Error(settings.message);
    const closed=$('#vr-hardware-closed').value,opened=$('#vr-hardware-open').value;
    if((closed==='')!==(opened===''))throw Error('夹爪行程需要同时填写或同时留空');
    const result=await request('start',{config:settings.config,armId:$('#vr-hardware-arm').value,
     speedDegS:Number($('#vr-hardware-speed').value),confirmed:true,
     gripper:closed===''?null:{closedDeg:Number(closed),openDeg:Number(opened)},
     positionOnly:$('#vr-hardware-solver').value==='position',
     positionGain:Number($('#vr-gain').value),orientation:$('#vr-rotation').checked,gripperEnabled:$('#vr-gripper').checked});
    state=result;token=result.viewerToken;
    if(cancelStart||document.hidden){await stop('页面已切换，本次真机 VR 已停止');return;}
   }else {
    state=await request('command',{action:{'vr/reset':'grasp','vr/exit':'exit','simulation/enable':'follow','simulation/disable':'pause'}[path]});
    if(!state.active)token=null;
   }
   message(state.message);
  }catch(error){message(error.message,true);}
  finally{busy=false;if(!state.active)$('#vr-hardware-confirm').checked=false;render();}
 }
 $('#vr-execution').addEventListener('change',async()=>{
  if(state.active){render();return;}
  mode=$('#vr-execution').value;
  if(mode==='simulation') {
   try{state=await request('simulation',{});}catch(e){mode='hardware';message(e.message,true);}
   if(mode==='simulation'){control.querySelector('[data-action="vr/enter"]').textContent='进入 VR 模式';control.querySelector('[data-action="vr/exit"]').textContent='退出 VR 模式';}
  }
  render();
 });
 for(const id of [...configFields,'vr-gain','vr-rotation','vr-gripper'])$('#'+id).addEventListener('change',()=>{
  $('#vr-hardware-confirm').checked=false;
  if(state.active)stop('参数已改变，请重新确认并进入真机 VR');
  try{localStorage.setItem('robostudio.vr-hardware.v1',JSON.stringify(Object.fromEntries(configFields.map(id=>[id,$('#'+id).value]))));}catch{}
  render();
 });
 $('#vr-hardware-use-limit').onclick=()=>{
  $('#vr-hardware-speed').value=String(settings?.maxSpeedDegS||10);
  $('#vr-hardware-speed').dispatchEvent(new Event('change'));
 };
 $('#vr-hardware-confirm').addEventListener('change',render);$('#vr-hardware-stop').onclick=()=>stop();
 const cancel=()=>{cancelStart=true;if(token)stop('RS 页面切至后台，已停止真机 VR');};
 document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();});window.addEventListener('blur',cancel);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&token)cancel();});
 window.addEventListener('pagehide',()=>{if(token)fetch('/api/hardware/vr/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});});
 window.addEventListener('s1:function-page',event=>{
  if(!['xr-control','xr-data','xr-connection','capture-session'].includes(event.detail.id)){
   cancelStart=true;
   if(token)stop('已离开 AR/VR 页面，停止真机 VR');
  }
 });
 window.addEventListener('s1:backend-disconnected',cancel);
 async function poll() {
  try {
   if(!settings){
    const r=await fetch('/api/hardware/mouse/settings');
    if(r.ok){
     settings=await r.json();
     const calibration=settings.gripperCalibrations?.[$('#vr-hardware-arm').value];
     if(calibration){
      $('#vr-hardware-closed').value=calibration.closedDeg;$('#vr-hardware-open').value=calibration.openDeg;
     }
    }
   }
   const fresh=await request(token?'touch':'state',token?{viewerToken:token}:undefined);state=fresh;
   if(state.selected)mode='hardware';if(!state.active)token=null;
   if(state.message!==last){message(state.message);last=state.message;}
  }catch(error){if(token){token=null;message('真机 VR 通信中断，停止保活；请检查实体机械臂。'+error.message,true);}}
  finally{render();setTimeout(poll,180);}
 }
 poll();
 return {handles:path=>mode==='hardware'&&['vr/enter','vr/reset','vr/exit','simulation/enable','simulation/disable'].includes(path),action,render};
}
