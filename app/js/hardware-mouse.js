const $=selector=>document.querySelector(selector);

// Explicit takeover only; neither saved preferences nor polling can start motion.
export class HardwareMouse {
  constructor(session) {
    this.session=session;this.active=false;this.sequence=0;this.tail=Promise.resolve();this.ioBusy=false;
    const panel=document.createElement('section');panel.className='hardware-mouse';panel.id='hardware-mouse';
    panel.innerHTML=`<div class="control-heading"><h2>真机鼠标控制</h2><span id="mouse-hardware-mode">仅仿真</span></div>
      <label>目标机械臂<select id="mouse-hardware-arm"><option value="A">机械臂 A</option><option value="B">机械臂 B</option></select></label>
      <label>关节速度上限<input id="mouse-hardware-speed" type="number" min="0.5" max="10" step="0.5" value="3"><span>°/s</span></label>
      <details id="mouse-gripper-config"><summary>夹爪行程配置</summary><p>填写已核对的实际电机角度；留空时只控制六关节，夹爪保持原状。</p>
        <label>闭合角度<input id="mouse-gripper-closed" type="number" min="-170" max="170" step="0.1" placeholder="未标定"><span>°</span></label>
        <label>张开角度<input id="mouse-gripper-open" type="number" min="-170" max="170" step="0.1" placeholder="未标定"><span>°</span></label>
        <button id="mouse-gripper-apply" disabled>应用已核对行程并启用夹爪</button>
        <p>跟随中也可应用行程；只对齐当前夹爪读数，不自动开合。之后滑块、按钮和滚轮才会驱动夹爪。</p>
      </details>
      <label class="check-row"><input id="mouse-hardware-confirm" type="checkbox">已核对目标、关节零位及方向，工作范围内无人</label>
      <div class="hardware-mouse-actions"><button id="mouse-hardware-start" disabled>对齐并开启真机控制</button><button id="mouse-hardware-stop" disabled>停止真机跟随</button></div>
      <p id="mouse-hardware-status" role="status">仅仿真；先在“初始化与复位”中使能，再开启真机控制。</p>
      <p class="hardware-mouse-note">开启时画面对齐真机，不自动回零。末端使用模型基座 / TCP；请先核对实际工具位置。鼠标目标限速执行；Esc、切出窗口或离开鼠标控制页停止跟随。软件停止不等同于硬件急停，且不自动失能。</p>`;
    $('.control-content').prepend(panel);this.panel=panel;
    const gripperStatus=document.createElement('div');gripperStatus.className='gripper-control-status';
    gripperStatus.innerHTML='<span id="mouse-gripper-status" role="status"></span><button id="mouse-gripper-configure" hidden>配置夹爪行程</button>';
    $('.gripper-section .control-heading').after(gripperStatus);
    this.fields=['#mouse-hardware-arm','#mouse-hardware-speed','#mouse-gripper-closed','#mouse-gripper-open'];
    try {
      const saved=JSON.parse(localStorage.getItem('robostudio.mouse-hardware.v1')||'null');
      if(saved)for(const id of this.fields)if(saved[id]!==undefined)$(id).value=saved[id];
    }catch{}
    for(const id of this.fields)$(id).addEventListener('change',()=>{
      $('#mouse-hardware-confirm').checked=false;
      if(this.active&&!id.startsWith('#mouse-gripper-'))this.stop('控制参数改变，请重新确认并开启');
      if(id.startsWith('#mouse-gripper-'))this.gripperDraft=true;
      try{localStorage.setItem('robostudio.mouse-hardware.v1',JSON.stringify(Object.fromEntries(this.fields.map(id=>[id,$(id).value]))));}catch{}
      this.render();
    });
    $('#mouse-hardware-confirm').addEventListener('change',()=>this.render());
    $('#mouse-hardware-start').addEventListener('click',()=>this.start());
    $('#mouse-hardware-stop').addEventListener('click',()=>this.stop());
    $('#mouse-gripper-configure').onclick=()=>{
      $('#mouse-gripper-config').open=true;
      $('#mouse-gripper-config').scrollIntoView({block:'center',behavior:'smooth'});
      $('#mouse-gripper-closed').focus({preventScroll:true});
    };
    $('#mouse-gripper-apply').onclick=()=>this.configureGripper();
    window.addEventListener('s1:function-page',event=>{
      const mouse=['joints','pose'].includes(event.detail.id);panel.hidden=!mouse;
      if(!mouse)this.cancelStart=true;
      if(!mouse && this.active)this.stop('已离开鼠标控制页，停止真机跟随');
    });
    window.addEventListener('blur',()=>{this.cancelStart=true;if(this.active)this.stop('窗口失去焦点，已停止真机跟随');});
    document.addEventListener('visibilitychange',()=>{if(document.hidden){this.cancelStart=true;if(this.active)this.stop('页面进入后台，已停止真机跟随');}});
    document.addEventListener('keydown',event=>{if(event.key==='Escape' && this.active)this.stop('Esc 停止真机跟随');});
    window.addEventListener('pagehide',()=>{
      if(this.active)fetch('/api/hardware/mouse/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});
    });
    window.addEventListener('s1:backend-disconnected',()=>{if(this.active)this.stop('后端连接中断，已停止真机跟随');});
    this.load();this.timer=setInterval(()=>this.pulse(),150);
  }

  async request(path,body) {
    const response=await fetch(`/api/hardware/mouse/${path}`,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(3000)});
    const result=await response.json();if(!response.ok)throw Error(result.message||'真机控制请求失败');return result;
  }

  status(text,error=false) {
    $('#mouse-hardware-status').textContent=text;$('#mouse-hardware-status').classList.toggle('result-error',error);
  }

  async load() {
    try {
      this.settings=await this.request('settings');
      $('#mouse-hardware-arm').options[1].disabled=this.settings.config.layout==='single';
      if(this.settings.config.layout==='single')$('#mouse-hardware-arm').value='A';
      const calibration=this.settings.gripperCalibrations?.[$('#mouse-hardware-arm').value];
      if(calibration&&!this.gripperDraft){
        $('#mouse-gripper-closed').value=calibration.closedDeg;$('#mouse-gripper-open').value=calibration.openDeg;
      }
      const state=await this.request('state');this.foreign=state.active;
      if(state.active)this.status('另一页面已开启真机控制；可点击停止后重新接管。');
    }catch(error){this.status('真机鼠标服务未就绪：'+error.message,true);}
    this.render();
  }

  render() {
    $('#mouse-hardware-mode').textContent=this.active?'真机 · 实际反馈':this.foreign?'真机 · 已被接管':'仅仿真';
    this.panel.classList.toggle('hardware-mouse-active',this.active);
    $('#mouse-hardware-start').disabled=this.active||this.foreign||this.busy||this.stopping||!this.settings||!$('#mouse-hardware-confirm').checked||!this.session.ready;
    $('#mouse-hardware-stop').disabled=this.busy||(!this.active&&!this.foreign);
    for(const id of this.fields)$(id).disabled=this.busy||(this.active&&!id.startsWith('#mouse-gripper-'));
    $('#mouse-hardware-confirm').disabled=this.active||this.busy;
    for(const id of ['#home-pose','#vr-grab-pose'])$(id).disabled=this.busy||this.stopping||this.foreign||!this.session.ready;
    $('#mouse-gripper-apply').disabled=!this.active||this.busy||this.stopping||$('#mouse-gripper-closed').value===''||$('#mouse-gripper-open').value==='';
    for(const control of document.querySelectorAll('#gripper-slider,[data-gripper]'))control.disabled=this.active&&!this.gripper;
    $('#mouse-gripper-status').textContent=this.active?this.gripper?
      (this.gripperDraft?'当前使用已应用的行程；修改后请点击应用。':'真机夹爪已接入 · 开度按已标定行程换算'):
      '真机夹爪未标定，开合暂未接管；当前 40% 是模型开度。':'仿真夹爪 · 真机开合需开启真机控制并配置行程';
    $('#mouse-gripper-configure').hidden=!this.active;
    if(this.active)for(const id of ['#simulation-run','#simulation-pause','#simulation-reset'])$(id).disabled=true;
  }

  clearPending() {
    const session=this.session;
    session.pending=null;session.desiredJoints=session.desiredGripper=null;
    clearTimeout(session.flushTimer);session.flushTimer=null;
  }

  async start() {
    if(this.busy||this.stopping||this.active||!$('#mouse-hardware-confirm').checked)return;
    this.busy=true;this.cancelStart=false;this.render();
    this.clearPending();this.session.mouse.stop(true);
    try {
      // Drain pre-takeover simulation commands so none can become real targets.
      if(this.session.busy||this.session.commands.length)throw Error('请等待当前仿真操作结束后再开启真机控制');
      this.settings=await this.request('settings');
      const closed=$('#mouse-gripper-closed').value,opened=$('#mouse-gripper-open').value;
      if((closed==='')!==(opened===''))throw Error('夹爪闭合和张开角度需要同时填写，或同时留空');
      const gripper=closed===''?null:{closedDeg:Number(closed),openDeg:Number(opened)};
      const result=await this.request('start',{config:this.settings.config,armId:$('#mouse-hardware-arm').value,
        speedDegS:$('#mouse-hardware-speed').valueAsNumber,gripper,confirmed:true});
      if(this.cancelStart||document.hidden){await this.request('stop',{});throw Error('界面已切换，本次开启已取消');}
      this.token=result.token;this.sequence=0;this.active=true;this.foreign=false;this.gripper=result.gripperAvailable;
      this.gripperDraft=false;
      this.session.apply(result.simulation);this.session.syncTarget();this.session.viewport.fit();this.status(result.message);
      this.session.message('真机已对齐 · 鼠标输入将驱动实体机械臂');
    }catch(error){this.status(error.message,true);}
    finally{this.busy=false;$('#mouse-hardware-confirm').checked=false;this.render();}
  }

  send(command) {
    if(command?.type==='joints')command={...command,joints:command.joints.map((q,i)=>{
      const [low,high]=this.session.state.joints[i].limits;return Math.max(low,Math.min(high,q));
    })};
    const token=this.token;
    this.ioBusy=true;
    const job=this.tail.catch(()=>{}).then(async()=>{
      if(!this.active||token!==this.token)throw Error('真机控制已停止，旧鼠标目标已丢弃');
      const result=await this.request('input',{token,sequence:++this.sequence,...(command?{command}:{})});
      if(!result.active)throw Error(result.message);
      if(this.active&&token===this.token){this.session.apply(result.simulation);this.status(result.message);this.render();}
      return result.simulation;
    });
    this.tail=job;
    job.finally(()=>{if(this.tail===job)this.ioBusy=false;}).catch(()=>{});
    return job;
  }

  async pulse() {
    if(!this.active||this.ioBusy||document.hidden)return;
    const token=this.token;
    try{await this.send();}catch(error){if(this.token===token)await this.stop(error.message,true);}
  }

  async control(command) {
    const token=this.token;
    try{return await this.send(command);}
    catch(error){if(this.token===token)await this.stop(error.message,true);throw error;}
  }

  async hold() {
    if(!this.active)return;
    this.clearPending();
    try{await this.control({type:'hold'});}catch{}
  }

  async configureGripper() {
    if(!this.active||this.busy||this.stopping)return;
    this.busy=true;this.render();this.clearPending();this.session.mouse.stop(true);
    const token=this.token;
    try{
      await this.hold();
      if(!this.active||this.token!==token)return;
      const simulation=await this.control({type:'gripper-config',confirmed:true,gripper:{
        closedDeg:$('#mouse-gripper-closed').valueAsNumber,openDeg:$('#mouse-gripper-open').valueAsNumber}});
      if(!this.active||this.token!==token)return;
      this.gripper=true;this.gripperDraft=false;this.session.apply(simulation);this.session.syncTarget();
      this.status('夹爪行程已应用，已对齐当前开度；滑块、按钮与滚轮现在可控制真机夹爪');
    }catch(error){this.status(error.message,true);}
    finally{this.busy=false;this.render();}
  }

  async stop(reason='已停止真机跟随；保持当前目标，不自动失能',error=false) {
    if(this.stopping)return;
    this.cancelStart=true;this.stopping=true;this.active=false;this.token=null;this.clearPending();this.session.mouse.stop(true);this.render();
    try {
      const result=await this.request('stop',{});this.foreign=false;
      this.session.apply(result.simulation);this.session.syncTarget();this.status(reason,error);
    }catch(e){this.status(reason+'；停止回执未收到，页面看门狗将停止下发，请检查真机。',true);}
    finally {this.stopping=false;$('#mouse-hardware-confirm').checked=false;this.render();}
  }
}
