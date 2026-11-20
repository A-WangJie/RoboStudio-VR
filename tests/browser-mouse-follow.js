const $ = selector => document.querySelector(selector);
const checks = [];
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
const assert = (condition,message) => {if(!condition)throw Error(message);checks.push(message);};
const wait = async predicate => {
  for(let i=0;i<180;i++){if(await predicate())return;await delay(50);}
  throw Error('等待鼠标跟随状态超时');
};
const state = async () => (await fetch('/api/sim/state')).json();
const change = (id,value) => {$(id).value=value;$(id).dispatchEvent(new Event('change',{bubbles:true}));};
function finish(result) {const output=document.createElement('pre');output.id='test-result';output.hidden=true;output.textContent=JSON.stringify(result);document.body.append(output);}
try {
  await wait(()=>document.body.dataset.workbenchReady==='true' && $('#loading').hidden);
  $('#pose-tab').click();$('#position-only').checked=true;
  change('#drag-mode','follow');$('#drag-toggle').click();
  const canvas=$('#viewport canvas'),rect=canvas.getBoundingClientRect();
  const center=[rect.left+rect.width*.55,rect.top+rect.height*.5];
  canvas.setPointerCapture=()=>{};canvas.releasePointerCapture=()=>{};
  const pointer=(type,point=center,buttons=0)=>canvas.dispatchEvent(new PointerEvent(type,{clientX:point[0],clientY:point[1],pointerId:1,pointerType:'mouse',button:type==='pointermove'?-1:0,buttons,bubbles:true,cancelable:true}));
  const wheel=deltaY=>canvas.dispatchEvent(new WheelEvent('wheel',{deltaY,bubbles:true,cancelable:true}));
  const camera=()=>window.s1Studio.snapshot().camera;
  const scale=percent=>{
    $('#follow-scale').value=String(percent);
    $('#follow-scale').dispatchEvent(new Event('input',{bubbles:true}));
  };
  assert($('#follow-scale').value==='30' && $('#follow-scale-value').textContent==='30%','长跟随默认使用30%的较慢映射');
  const realFetch=window.fetch,poses=[];
  window.fetch=(url,options)=>{
    if(url==='/api/sim/command' && options?.body) {
      const payload=JSON.parse(options.body);
      if(payload.type==='pose')poses.push(payload);
    }
    return realFetch(url,options);
  };
  const lengths=[];
  for(const percent of [100,25]) {
    scale(percent);
    const start=await state(),sent=poses.length;
    await wait(()=>window.s1Studio.snapshot().backend.sequence>=start.sequence);
    pointer('pointerdown',center,1);
    pointer('pointermove',[center[0],center[1]-6],1);
    pointer('pointerup',[center[0],center[1]-6],0);
    await wait(async()=>(await state()).command_count>start.command_count);
    await delay(100);
    assert(poses.length===sent+1,`${percent}%比例正常发送单个跟随目标`);
    const delta=poses.at(-1).position.map((value,i)=>value-start.tcp.position[i]);
    lengths.push(Math.hypot(...delta));
    const actual=await state();
    assert(Math.hypot(...actual.tcp.position.map((value,i)=>value-poses.at(-1).position[i]))<.0005,`${percent}%比例目标通过实际逆解应用`);
  }
  assert(Math.abs(lengths[1]/lengths[0]-.25)<.002,'25%比例将相同鼠标移动的末端目标位移缩小为四分之一');
  assert(localStorage.getItem('robostudio.mouse-follow-scale.v1')==='25','跟随映射比例保存到本地配置');
  const beforeScaleChange=await state();
  pointer('pointerdown',center,1);
  scale(10);
  assert(canvas.dataset.mouseFollow==='idle','跟随中调整比例会停止原手势');
  await delay(100);
  assert((await state()).command_count===beforeScaleChange.command_count,'调整比例本身不会发送移动目标或引起跳动');
  scale(100);
  window.fetch=realFetch;
  const before=await state(),beforeCamera=camera();
  pointer('pointerdown',center,1);await delay(90);
  assert((await state()).command_count===before.command_count,'开始长跟随时不跳动、不发送新目标');
  for(let i=1;i<=16;i++) {pointer('pointermove',[center[0],center[1]-i*.12],1);await delay(16);}
  await wait(async()=>(await state()).command_count>before.command_count+1);
  assert(canvas.dataset.mouseFollow==='hold','按住左键期间持续发送目标，未被连续事件阻塞');
  wheel(-100);
  for(let i=17;i<=22;i++){pointer('pointermove',[center[0],center[1]-i*.12],1);await delay(16);}
  pointer('pointerup',[center[0],center[1]-22*.12],0);
  await wait(async()=>Math.abs((await state()).target_gripper-45)<.01);
  const moved=await state();
  assert(Math.abs(moved.tcp.position[2]-before.tcp.position[2])>.0001,'长跟随驱动实际逆解和TCP移动');
  assert(camera().every((v,i)=>Math.abs(v-beforeCamera[i])<1e-8),'拖拽和滚轮不会同时旋转或缩放相机');
  assert(canvas.dataset.mouseFollow==='idle','松开左键停止按住拖拽');
  await delay(150);const released=(await state()).command_count;
  pointer('pointermove',[center[0],center[1]-5],0);await delay(100);
  assert((await state()).command_count===released,'松开后鼠标移动不会继续发送目标');

  change('#follow-behavior','continuous');
  pointer('pointerdown',center,1);pointer('pointerup',center,0);
  pointer('pointermove',[center[0]+.6,center[1]],0);
  await wait(async()=>(await state()).command_count>released);
  assert(canvas.dataset.mouseFollow==='continuous','点击后无需按住即可持续跟随');
  pointer('pointerdown',[center[0]+.6,center[1]],1);pointer('pointerup',center,0);
  assert(canvas.dataset.mouseFollow==='idle','再次点击停止持续跟随');
  pointer('pointerdown',center,1);pointer('pointerup',center,0);
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert(canvas.dataset.mouseFollow==='idle','Esc停止长跟随');
  pointer('pointerdown',center,1);pointer('pointerup',center,0);
  window.dispatchEvent(new Event('blur'));
  assert(canvas.dataset.mouseFollow==='idle','切换窗口停止长跟随');
  pointer('pointerdown',center,1);pointer('pointerup',center,0);
  canvas.dispatchEvent(new PointerEvent('pointercancel',{pointerId:1,pointerType:'mouse'}));
  assert(canvas.dataset.mouseFollow==='idle','指针取消停止长跟随');

  change('#drag-mode','translate');
  // A stale drag marker must not move the arm back when only the gripper changes.
  const jointBefore=(await state()).target_joints[0];
  const jointInput=$('#joint-1');
  jointInput.value=String(jointBefore*180/Math.PI+.1);
  jointInput.dispatchEvent(new Event('input'));
  await wait(async()=>Math.abs((await state()).target_joints[0]-jointBefore)>.001);
  await delay(100);
  const beforeWheel=await state();
  wheel(100);await wait(async()=>Math.abs((await state()).target_gripper-40)<.01);
  assert(true,'普通平移拖拽模式也支持滚轮闭合夹爪');
  assert((await state()).target_joints.every((v,i)=>Math.abs(v-beforeWheel.target_joints[i])<1e-7),'单独滚轮操作夹爪不会恢复过期的末端目标');
  for(let i=0;i<14;i++)wheel(-100);
  await wait(async()=>Math.abs((await state()).target_gripper-100)<.01);
  assert(true,'快速滚轮累计到100%，不会丢失或超出夹爪范围');
  $('#drag-toggle').click();
  const grip=(await state()).target_gripper,cam=camera();
  wheel(100);await delay(250);
  assert(Math.abs((await state()).target_gripper-grip)<.01,'关闭拖拽后滚轮不再控制夹爪');
  assert(camera().some((v,i)=>Math.abs(v-cam[i])>1e-5),'关闭拖拽后恢复滚轮缩放');
  $('#drag-toggle').click();change('#drag-mode','follow');
  pointer('pointerdown',center,1);pointer('pointerup',center,0);
  pointer('pointermove',[rect.right-1,rect.top+1],0);
  await wait(()=>$('#pose-result').classList.contains('result-error'));
  assert(canvas.dataset.mouseFollow==='idle','不可达目标被拒绝后停止长跟随');
  // Restore the fixture and frame the whole arm for the preview.
  const restored=await fetch('/api/sim/command',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({type:'joints',joints:before.target_joints,gripper:40})});
  if(!restored.ok)throw Error('无法恢复测试姿态');
  const restoredState=await restored.json();
  await wait(()=>window.s1Studio.snapshot().backend.sequence>=restoredState.sequence);
  $('#pose-sync').click();
  $('#pose-apply').click();
  await wait(()=>!$('#pose-result').classList.contains('result-error'));
  $('#fit-view').click();
  change('#follow-behavior','hold');
  scale(30);
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  finish({ok:true,checks});
}catch(error){finish({ok:false,checks,error:error.stack});}
