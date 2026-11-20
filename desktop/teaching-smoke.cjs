// Runs only inside the isolated desktop smoke-test profile.
const fs = require('node:fs');
const path = require('node:path');
module.exports = async ({js, wait, check, screenshot, configPath}) => {
  await js(`(() => {
    document.querySelector('[data-category="control"]').click();
    document.querySelector('.function-menu [data-subcategory="teaching"]').click();
    document.querySelector('.function-menu [data-function-page="teaching-session"]').click();
    const field=document.querySelector('[data-config-page="teaching-session"] [data-arm-path="connection.layout"]');
    field.value='dual';field.dispatchEvent(new Event('input',{bubbles:true}));
    document.querySelector('[data-config-page="teaching-session"] [data-arm-action="save"]').click();
  })()`);
  await wait(()=>js('document.querySelector("[data-config-page=teaching-session] .arm-save-state").textContent.includes("配置已保存")'));
  const teachingFile=path.join(path.dirname(configPath),'arms.json');
  const teachingConfig=JSON.parse(fs.readFileSync(teachingFile));
  check(teachingConfig.connection.layout==='dual' && teachingConfig.teaching.pairs.length===2,
    'Teaching configuration persists through desktop IPC with shared single/dual layout');
  const teachingRead=await js('window.s1Desktop.armConfig()');
  check(teachingRead.config.teaching.holdToEnable===true && teachingRead.config.connection.layout==='dual',
    'Desktop configuration reader retains teaching parameters');
  check(await js(`document.querySelector('[data-category="arm-config"]').nextElementSibling.dataset.category==='control'`),
    'Unified arm control appears immediately after arm configuration');
  await screenshot('teaching-desktop.png');
};
