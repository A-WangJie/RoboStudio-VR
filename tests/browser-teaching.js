const $ = selector => document.querySelector(selector);
const checks = [];
const wait = async predicate => {
  for (let i=0;i<200;i++) {if(await predicate())return;await new Promise(r=>setTimeout(r,60));}
  throw Error('等待界面更新超时');
};
const assert = (condition,message) => {if(!condition)throw Error(message);checks.push(message);};
const change = (selector,value) => {const field=$(selector);field.value=value;field.dispatchEvent(new Event('input',{bubbles:true}));};
const open = (category,page) => {
  const nested = category === 'teaching';
  $(`[data-category="${nested ? 'control' : category}"]`).click();
  if (nested) $('.function-menu [data-subcategory="teaching"]').click();
  $(`.function-menu [data-function-page="${page}"]`).click();
};
const readState = async () => (await fetch('/api/sim/state')).json();
function finish(result) {const output=document.createElement('pre');output.id='test-result';output.hidden=true;output.textContent=JSON.stringify(result);document.body.append(output);}
try {
  await wait(()=>document.body.dataset.workbenchReady==='true');
  await wait(()=>$('#loading').hidden);
  const initial=await readState();
  assert($('[data-category="arm-config"]').nextElementSibling===$('[data-category="control"]'),'机械臂控制位于机械臂配置右侧');
  const mapping='[data-config-page="teaching-mapping"]';
  const session='[data-config-page="teaching-session"]';
  const pairing='[data-config-page="arm-teaching"]';
  const field=path=>`${pairing} [data-arm-path="${path}"]`;
  if(sessionStorage.getItem('teaching-reload')!=='yes') {
    open('teaching','teaching-session');
    assert([...$(session).querySelectorAll('.arm-operation-grid button')].filter(b=>b.textContent.includes('示教')).every(b=>b.disabled),'硬件未接入时不能假启动示教');
    change(`${session} [data-arm-path="connection.layout"]`,'dual');
    assert([...document.querySelectorAll('[data-arm-path="connection.layout"]')].every(f=>f.value==='dual'),'单/双臂数量在机械臂配置与示教模块同步');
    open('arm-config','arm-teaching');
    change(field('teaching.pairs.0.leader.device'),'can0');
    $(pairing+' [data-arm-action="validate"]').click();
    assert($(pairing+' .arm-save-state').textContent.includes('重复'),'主从接口冲突会阻止校验');
    change(field('teaching.pairs.0.leader.device'),'can2');
    change(field('teaching.pairs.1.leader.device'),'can3');
    change(field('teaching.pairs.0.leader.bitrate'),'500000');
    change(field('teaching.pairs.1.leader.bitrate'),'500000');
    open('teaching','teaching-mapping');
    change(mapping+' [data-arm-path="teaching.pairs.0.direction.0"]','-1');
    change(mapping+' [data-arm-path="teaching.pairs.0.scale.0"]','1.5');
    change(mapping+' [data-arm-path="teaching.pairs.0.offsetDegrees.0"]','10');
    change(mapping+' [data-teaching-preview="0"][data-joint="0"]','30');
    assert($(mapping+' [data-teaching-output="0"]').textContent.includes('-35.0'),'离线预览按方向、比例和偏移计算');
    change(mapping+' [data-arm-path="teaching.pairs.0.direction.1"]','-1');
    change(mapping+' [data-teaching-preview="0"][data-joint="1"]','30');
    assert($(mapping+' [data-teaching-output="0"]').textContent.includes('超出限位：J2'),'离线预览明确报告关节超限');
    $(mapping+' [data-arm-action="save"]').click();
    await wait(()=>$(mapping+' .arm-save-state').textContent.includes('配置已保存'));
    let saved=JSON.parse(localStorage.getItem('robostudio.arm-config.v1'));
    assert(saved.teaching.pairs[0].direction[1]===-1 && saved.connection.layout==='dual','映射与机械臂配置共同保存');
    open('arm-config','arm-connection');
    change('[data-config-page="arm-connection"] [data-arm-path="connection.layout"]','single');
    assert([...document.querySelectorAll('[data-teaching-index="1"]')].every(f=>f.disabled),'单臂模式禁用B组');
    $('[data-config-page="arm-connection"] [data-arm-action="save"]').click();
    await wait(()=>$('[data-config-page="arm-connection"] .arm-save-state').textContent.includes('配置已保存'));
    saved=JSON.parse(localStorage.getItem('robostudio.arm-config.v1'));
    assert(saved.teaching.pairs[1].leader.device==='can3','切换单臂保留B组配对');
    const after=await readState();
    assert(after.command_count===initial.command_count,'配置和预览没有下发任何机械臂命令');
    sessionStorage.setItem('teaching-checks',JSON.stringify(checks));
    sessionStorage.setItem('teaching-reload','yes');location.reload();
  } else {
    checks.push(...JSON.parse(sessionStorage.getItem('teaching-checks')));
    assert($(field('teaching.pairs.1.leader.device')).value==='can3','重新加载后恢复已保存的主从配对');
    assert($(`${session} [data-arm-path="connection.layout"]`).value==='single','重新加载后恢复共享数量设置');
    open('teaching','teaching-session');
    assert($(session+' [data-teaching-summary="0"]').textContent.includes('can2'),'示教概览读取已保存的主臂配置');
    finish({ok:true,checks});
  }
}catch(error){finish({ok:false,checks,error:error.stack});}
