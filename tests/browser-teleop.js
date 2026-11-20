import * as THREE from '/vendor/three.module.js';

const log = [];
const $ = selector => document.querySelector(selector);
const state = async () => (await fetch('/api/sim/state')).json();
const wait = async predicate => {
  for (let i=0;i<250;i++) { if (await predicate()) return; await new Promise(resolve=>setTimeout(resolve,40)); }
  throw new Error('Timed out waiting for browser state');
};
const assert = (condition, message) => { if (!condition) throw new Error(message); log.push(message); };
const change = (selector, value) => { const element=$(selector); element.value=value; element.dispatchEvent(new Event('change',{bubbles:true})); };

try {
  await wait(()=>window.s1Studio?.snapshot().backend);
  assert($('#backend-state').textContent.includes('MuJoCo'),'MuJoCo backend connected');
  $('#pose-tab').click(); $('#pose-sync').click();
  const initial=await state();
  $('#pose-z').value=String(initial.tcp.position[2]*1000+10);
  $('#pose-apply').click();
  await wait(()=>$('#pose-result').textContent.includes('逆解已应用'));
  const raised=await state();
  assert(Math.abs(raised.tcp.position[2]-initial.tcp.position[2]-.01)<.0005,'XYZ input drives inverse kinematics');
  $('#pose-roll').value='2'; $('#pose-apply').click();
  await wait(async()=>(await state()).command_count>raised.command_count);
  const rotated=await state();
  assert(Math.abs(rotated.tcp.rpy_deg[0]-2)<1,'Orientation input drives inverse kinematics');
  const accepted=[...rotated.joints];
  $('#pose-x').value='5000'; $('#pose-apply').click();
  await wait(()=>$('#pose-result').textContent.includes('超出'));
  assert((await state()).joints.every((q,i)=>Math.abs(q-accepted[i])<1e-8),'Unreachable target preserves accepted pose');
  $('#joint-tab').click();
  // Zero is now a valid home pose. Check a real obstacle collision instead.
  const obstacle=$('#obstacle-enabled');obstacle.checked=true;obstacle.dispatchEvent(new Event('change'));
  await wait(async()=>(await state()).obstacle);
  const colliding=[.5693844361,1.867324172,.8398506467,-1.046914993,.8367071885,.5422002931];
  for(let i=1;i<=6;i++) {const input=$('#joint-value-'+i);input.value=String(colliding[i-1]*180/Math.PI);input.dispatchEvent(new Event('blur'));}
  await wait(()=>$('#collision-state').classList.contains('collision-alert'));
  assert((await state()).joints.every((q,i)=>Math.abs(q-accepted[i])<1e-8),'Colliding joint path rejected in UI');
  $('#simulation-reset').click();
  await wait(()=>!$('#collision-state').classList.contains('collision-alert'));
  obstacle.checked=false;obstacle.dispatchEvent(new Event('change'));
  await wait(async()=>!(await state()).obstacle);
  obstacle.checked=true;obstacle.dispatchEvent(new Event('change'));
  await wait(async()=>(await state()).obstacle);
  assert(true,'Obstacle toggle synchronizes backend and viewport');
  change('#simulation-mode','dynamic');
  await wait(async()=>(await state()).mode==='dynamic');
  $('#simulation-run').click();
  await wait(async()=>(await state()).running);
  await fetch('/test-step',{method:'POST'});
  const dynamic=await state();
  assert(dynamic.simulation_time>.4 && dynamic.running,'MuJoCo advances physical time with torque controller');
  // Hold an in-flight motion response while a pause and another slider input arrive.
  const realFetch=window.fetch;
  let release,held=false;
  const sent=[];
  const gate=new Promise(resolve=>{release=resolve;});
  window.fetch=async (url,options)=>{
    const response=await realFetch(url,options);
    if(url==='/api/sim/command') {
      sent.push(JSON.parse(options.body).type);
      if(sent.length===1){held=true;await gate;}
    }
    return response;
  };
  $('#joint-tab').click();
  const slider=$('#joint-1');slider.value='1';slider.dispatchEvent(new Event('input'));
  await wait(()=>held);
  $('#simulation-pause').click();
  slider.value='20';slider.dispatchEvent(new Event('input'));
  release();
  await wait(async()=>!(await state()).running);
  await new Promise(resolve=>setTimeout(resolve,200));
  window.fetch=realFetch;
  assert(JSON.stringify(sent)===JSON.stringify(['joints','pause']),'Pause survives an in-flight command and discards later queued motion');
  change('#simulation-mode','kinematic');
  await wait(async()=>(await state()).mode==='kinematic');
  const beforeReset=(await state()).revision;
  $('#simulation-reset').click();
  await wait(async()=>(await state()).revision>beforeReset && $('#pose-result').textContent==='仿真已重置');
  $('#pose-tab').click(); $('#pose-sync').click(); $('#drag-toggle').click();
  assert($('#drag-toggle').getAttribute('aria-pressed')==='true','Three-dimensional target handle enabled');
  // TransformControls updates its picking matrices during rendering. Wait for a
  // painted frame after attaching it, including under headless virtual time.
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  // Deliver pointer events through the actual TransformControls DOM handlers.
  const canvas=$('#viewport canvas'),rect=canvas.getBoundingClientRect();
  const diagnostics=window.s1Studio.snapshot();
  const camera=new THREE.PerspectiveCamera(36,rect.width/rect.height,.01,30);
  camera.up.set(0,0,1);camera.position.fromArray(diagnostics.camera);
  camera.lookAt(new THREE.Vector3().fromArray(diagnostics.cameraTarget));camera.updateMatrixWorld();
  const origin=new THREE.Vector3().fromArray((await state()).tcp.position);
  const factor=camera.position.distanceTo(origin)*Math.min(1.9*Math.tan(Math.PI*camera.fov/360)/camera.zoom,7)*.75/4;
  const project=point=>{const p=point.project(camera);return [rect.x+(p.x+1)*rect.width/2,rect.y+(1-p.y)*rect.height/2];};
  const pointer=(type,point,button=0)=>canvas.dispatchEvent(new PointerEvent(type,{clientX:point[0],clientY:point[1],button,buttons:type==='pointerup'?0:1,pointerId:1,pointerType:'mouse',bubbles:true}));
  canvas.setPointerCapture=()=>{};canvas.releasePointerCapture=()=>{};
  const count=(await state()).command_count;
  for(const axis of [new THREE.Vector3(0,0,1),new THREE.Vector3(1,0,0),new THREE.Vector3(0,1,0)]) {
    const a=project(origin.clone().addScaledVector(axis,factor*.8));
    const b=project(origin.clone().addScaledVector(axis,factor*.8+.005));
    pointer('pointermove',a);pointer('pointerdown',a);
    pointer('pointermove',b);pointer('pointerup',b);
    await new Promise(resolve=>setTimeout(resolve,120));
    if((await state()).command_count>count)break;
  }
  await wait(async()=>(await state()).command_count>count);
  assert(true,'Dragging a three-dimensional axis sends a real IK target');
  $('#drag-toggle').click(); $('#simulation-reset').click();
  await wait(async()=>(await state()).joints.every(q=>Math.abs(q)<1e-5));
  $('#pose-sync').click(); $('#drag-toggle').click();
  if(location.search.includes('disconnect')) {
    // A lost backend must freeze controls instead of silently accepting local poses.
    const frozen=window.s1Studio.snapshot().jointsRadians;
    window.fetch=async(url,options)=>{
      if(url==='/api/sim/state')throw new TypeError('Injected disconnected backend');
      return realFetch(url,options);
    };
    await wait(()=>$('#backend-state').textContent==='连接中断');
    slider.value='30';slider.dispatchEvent(new Event('input'));
    assert(slider.disabled && window.s1Studio.snapshot().jointsRadians.every((q,i)=>q===frozen[i]),'Backend disconnect freezes controls and preserves last confirmed model');
    window.fetch=realFetch;
  }
  const result=document.createElement('pre');result.id='test-result';result.hidden=true;
  result.textContent=JSON.stringify({ok:true,checks:log});document.body.appendChild(result);
} catch(error) {
  const result=document.createElement('pre');result.id='test-result';result.hidden=true;
  result.textContent=JSON.stringify({ok:false,error:error.stack,checks:log});document.body.appendChild(result);
}
