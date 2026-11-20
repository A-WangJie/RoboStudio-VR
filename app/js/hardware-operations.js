// Explicit user operations only. No startup, timer or saved flag sends commands.
export function installHardwareOperations({startup, current, isReady, setStatus, detectionBusy}) {
  const target=startup.querySelector('[data-hardware-target]');
  const confirm=startup.querySelector('[data-hardware-confirm]');
  const message=startup.querySelector('[data-hardware-operation-message]');
  const output=startup.querySelector('[data-hardware-state]');
  let busy=false, snapshot=null, lastKey='', operationError='';
  const selected=()=>({config:current(),armId:target.value});
  const key=value=>JSON.stringify({armId:value.armId,config:value.config});
  function render() {
    let value;try{value=selected();}catch{}
    const valid=!!value;
    if(value?.config.layout==='single') {
      target.options[1].disabled=true;
      if(target.value==='B'){target.value='A';value=selected();}
    } else target.options[1].disabled=false;
    const nextKey=valid?key(value):'';
    if(lastKey!==nextKey){confirm.checked=false;lastKey=nextKey;}
    const matching=snapshot && valid && key({config:snapshot.config,armId:snapshot.armId})===nextKey;
    const age=matching?Math.max(0,(Date.now()-snapshot.sampledAtMs)/1000):Infinity;
    const recent=matching && age<=10;
    const canEnable=recent && snapshot.complete && !snapshot.samples.some(s=>s.fault || !s.positionValid) && !operationError;
    for(const action of ['read','enable','disable']) {
      const button=startup.querySelector(`[data-hardware-action="${action}"]`);
      button.disabled=busy || detectionBusy() || !isReady() || !valid || (action==='enable' && (!canEnable || !confirm.checked));
      button.title=action==='enable'?'先读取完整状态，再勾选现场确认；使能会让电机输出力矩':action==='disable'?'撤去电机支撑；无需先读取状态':'查询实际角度、速度、力矩、温度和使能状态';
    }
    target.disabled=busy;confirm.disabled=busy;
    if(!snapshot)return;
    const heading=document.createElement('p');heading.className='hardware-state-heading';
    heading.textContent=matching?`${age>10?'历史':'最近'}真机读数 · ${snapshot.armId} / ${snapshot.device} · ${Math.floor(age)} 秒前`:'参数或目标已更改，旧读数已失效，请重新读取';
    const table=document.createElement('table');
    const header=document.createElement('tr');
    for(const text of ['节点','角度 °','状态']){const th=document.createElement('th');th.textContent=text;header.append(th);}
    const thead=document.createElement('thead');thead.append(header);table.append(thead);
    const body=document.createElement('tbody');
    for(const sample of snapshot.samples) {
      const row=document.createElement('tr');
      const name=sample.node===7?'夹爪':`J${sample.node}`;
      for(const text of [name,sample.positionDeg.toFixed(2),sample.positionValid?sample.state:'角度异常']) {
        const td=document.createElement('td');td.textContent=text;row.append(td);
      }
      row.classList.toggle('hardware-state-fault',sample.fault || !sample.positionValid);
      row.title=`${name} · 速度 ${sample.velocityRadS.toFixed(3)} rad/s · 力矩 ${sample.torqueNm.toFixed(3)} N·m · MOS ${sample.mosTemperatureC} ℃ · 线圈 ${sample.coilTemperatureC} ℃`;
      body.append(row);
    }
    table.append(body);
    const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='速度、力矩与温度';details.append(summary);
    const pre=document.createElement('pre');pre.textContent=snapshot.samples.map(s=>`${s.node===7?'夹爪':`J${s.node}`}  ${s.velocityRadS.toFixed(3)} rad/s  ${s.torqueNm.toFixed(3)} N·m\nMOS ${s.mosTemperatureC} ℃ / 线圈 ${s.coilTemperatureC} ℃`).join('\n');details.append(pre);
    // Avoid rebuilding the table on each elapsed-second refresh, preserving details state.
    const existing=output.querySelector('.hardware-state-heading');
    if(output.dataset.snapshot!==String(snapshot.sampledAtMs)) {
      output.replaceChildren(heading,table,details);output.dataset.snapshot=String(snapshot.sampledAtMs);
    } else if(existing)existing.textContent=heading.textContent;
    output.classList.toggle('hardware-state-stale',!recent || !!operationError);
  }
  async function operate(action) {
    if(busy || detectionBusy() || !isReady())return;
    let value;try{value=selected();}catch(e){message.textContent=e.message;return;}
    if(action==='enable' && !confirm.checked)return;
    busy=true;operationError='';
    message.textContent=action==='read'?'正在读取真机状态…':action==='enable'?'正在使能并核对节点反馈…':'正在失能并核对节点反馈…';render();
    try {
      const response=await fetch(`/api/hardware/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...value,confirmed:confirm.checked}),signal:AbortSignal.timeout(10000)});
      let result;try{result=await response.json();}catch{throw Error('真机服务尚未更新，请完整重启 RS');}
      if(!response.ok)throw Error(result.message||'真机操作失败');
      snapshot=result;
      message.textContent=`${result.armId} / ${result.device}：${result.message}`;
      if(result.sendError)message.textContent+=`；${result.sendError}`;
      message.classList.toggle('error',!result.verified);
      setStatus(message.textContent,!result.verified);
    } catch(e) {
      operationError=e.name==='TimeoutError'?'请求超时，真机结果未知；请重新读取状态':e.message;
      message.textContent=operationError;message.classList.add('error');setStatus(operationError,true);
    } finally {busy=false;if(action!=='read')confirm.checked=false;render();}
  }
  target.addEventListener('change',()=>{confirm.checked=false;message.textContent='操作目标已切换，请读取该机械臂的状态。';render();});
  confirm.addEventListener('change',render);
  return {render,operate,isBusy:()=>busy};
}
