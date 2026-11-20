const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {readArmConfig, saveArmConfig} = require('../desktop/arm-config.cjs');

test('offline config persists both independent arms without creating a file on read', async () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'arms-config-'));
  const filename=path.join(dir,'arms.json');
  try {
    const {config}=await readArmConfig(filename);
    assert.equal(fs.existsSync(filename),false);
    assert.equal(config.arms[0].bitrate,null);
    assert.equal(config.arms[0].resetDegrees,null);
    config.connection.layout='dual';
    config.arms[0].arSource='left'; config.arms[1].arSource='right';
    config.arms[1].device='can_right'; config.arms[1].basePose[1]=450;
    await saveArmConfig(filename,config);
    assert.deepEqual((await readArmConfig(filename)).config,config);
    const before=fs.readFileSync(filename,'utf8');
    const invalid = changes => {const draft=structuredClone(config); changes(draft); return draft;};
    for (const value of [
      invalid(c=>c.arms[1].device=c.arms[0].device),
      invalid(c=>c.arms[1].arSource='left'),
      invalid(c=>c.arms[0].resetDegrees=[0,0,175,0,0,0]),
      invalid(c=>c.arms[0].resetDegrees=[0,null,0,0,0,0]),
      invalid(c=>c.arms[0].device='can0;shutdown'),
      invalid(c=>c.arms[0].bitrate='500000'),
      invalid(c=>c.arms[0].positionScale=Infinity),
      invalid(c=>c.startup.requireEnable=false),
      invalid(c=>c.ar.holdToEnable=false),
    ]) {
      await assert.rejects(saveArmConfig(filename,value));
      assert.equal(fs.readFileSync(filename,'utf8'),before);
    }
    config.connection.layout='single';
    await saveArmConfig(filename,config);
    assert.equal((await readArmConfig(filename)).config.arms[1].device,'can_right');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('corrupt existing hardware config is reported rather than silently replaced', async () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'arms-invalid-'));
  const filename=path.join(dir,'arms.json');
  try {fs.writeFileSync(filename,'{broken'); await assert.rejects(readArmConfig(filename)); assert.equal(fs.readFileSync(filename,'utf8'),'{broken');}
  finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('older configurations gain VR defaults without losing arm mappings; invalid endpoints are rejected', async () => {
  const {defaultArmConfig,validateArmConfig}=await import('../app/js/arm-config-model.js');
  const old=defaultArmConfig(); delete old.ar.connection;
  old.arms[0].arSource='left'; old.arms[1].arSource='right';
  const next=validateArmConfig(old);
  assert.equal(next.ar.connection.host,'');
  assert.equal(next.ar.connection.port,8766);
  assert.deepEqual(next.arms,old.arms);
  for (const patch of [{host:'ws://192.168.1.2/path'},{port:123.5},{port:65536},{device:'unknown'},{autoReconnect:'true'}]) {
    assert.throws(()=>validateArmConfig({...next,ar:{...next.ar,connection:{...next.ar.connection,...patch}}}));
  }
});

test('legacy configs gain unassigned leaders without conflicting with existing CAN slots', async () => {
  const {defaultArmConfig,validateArmConfig}=await import('../app/js/arm-config-model.js');
  const old=defaultArmConfig();delete old.teaching;
  old.arms[0].device='can2';old.arms[1].device='can3';
  const result=validateArmConfig(old);
  assert.deepEqual(result.arms,old.arms);
  assert.equal(result.teaching.pairs[0].leader.device,'');
  assert.equal(result.teaching.holdToEnable,true);
});

test('teaching pairs persist with shared layout, while invalid mappings never replace saved config', async () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'teaching-config-'));
  const filename=path.join(dir,'arms.json');
  try {
    const {config}=await readArmConfig(filename);
    config.connection.layout='dual';
    config.teaching.pairs.forEach((p,i)=>{p.leader.device=`can${i+2}`;p.leader.bitrate=500000;});
    config.teaching.pairs[0].direction[0]=-1;
    config.teaching.pairs[1].offsetDegrees[2]=15;
    await saveArmConfig(filename,config);
    assert.deepEqual((await readArmConfig(filename)).config,config);
    const before=fs.readFileSync(filename,'utf8');
    for(const change of [
      c=>c.teaching.pairs[0].leader.device='can0',
      c=>c.teaching.pairs[1].leader.device='can2',
      c=>c.teaching.pairs[1].leader.device='can3;id',
      c=>c.teaching.pairs[0].direction[0]=0,
      c=>c.teaching.pairs[0].scale[0]=0,
      c=>c.teaching.pairs[0].offsetDegrees[0]=NaN,
      c=>c.teaching.pairs[0].direction=[],
      c=>c.teaching.holdToEnable=false,
      c=>c.teaching.rateHz=1,
    ]) {
      const draft=structuredClone(config);change(draft);
      await assert.rejects(saveArmConfig(filename,draft));
      assert.equal(fs.readFileSync(filename,'utf8'),before);
    }
    config.connection.layout='single';
    await saveArmConfig(filename,config);
    const next=(await readArmConfig(filename)).config;
    assert.equal(next.teaching.pairs[1].offsetDegrees[2],15);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('offline mapping reports limits without clamping the target', async () => {
  const {defaultTeachingConfig,mapTeachingJoints}=await import('../app/js/teaching-model.js');
  const {JOINT_LIMITS}=await import('../app/js/arm-config-model.js');
  const pair=defaultTeachingConfig().pairs[0];
  pair.direction[0]=-1;pair.scale[0]=1.5;pair.offsetDegrees[0]=10;
  const result=mapTeachingJoints(pair,[30,0,0,0,0,0],JOINT_LIMITS);
  assert.equal(result.target[0],-35);assert.deepEqual(result.violations,[]);
  pair.direction[1]=-1;
  const invalid=mapTeachingJoints(pair,[30,30,0,0,0,0],JOINT_LIMITS);
  assert.equal(invalid.target[1],-30);assert.deepEqual(invalid.violations,['J2']);
  assert.throws(()=>mapTeachingJoints(pair,[0,NaN,0,0,0,0],JOINT_LIMITS));
});
