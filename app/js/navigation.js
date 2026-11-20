// Shared by the command menus and the current project's navigation tree.
export function functionCategories(desktop = !!window.s1Desktop) {
  const leaf = (id, label) => ({id, label});
  return [
    {id: 'arm-config', label: '机械臂配置', icon: 'arm-config', items: [
      leaf('arm-connection', '连接与设备识别'), leaf('arm-devices', '机械臂参数'),
      leaf('arm-startup', '初始化与复位'), leaf('arm-teaching', '主从示教配置')]},
    {id: 'control', label: '机械臂控制', icon: 'robot', items: [
      {id: 'teaching', label: '从臂示教', icon: 'teaching', items: [
        leaf('teaching-session', '单 / 双臂主从示教'), leaf('arm-teaching', '主从配对与设备'),
        leaf('teaching-mapping', '关节映射与对齐'), leaf('teaching-guide', '示教操作说明')]},
      {id: 'mouse', label: '鼠标控制', icon: 'robot', items: [
        leaf('joints', '关节控制'), leaf('pose', '末端位姿 / 三维拖拽')]},
      {id: 'xr', label: 'AR / VR', icon: 'xr', items: [
        leaf('xr-connection', '设备与采集'), leaf('xr-control', '遥控操作'),
        leaf('xr-data', '手柄实时数据'), leaf('xr-guide', '使用说明')]},
    ]},
    {id: 'capture', label: '数据采集', icon: 'list', items: [leaf('capture-session', '任务与录制')]},
    {id: 'simulation', label: '仿真', icon: 'play', items: [leaf('simulation', '运行 / 暂停 / 重置与碰撞')]},
    {id: 'data', label: '数据', icon: 'list', items: [leaf('activity', '事件记录'), leaf('model', '项目与模型信息')]},
    {id: 'tools', label: '设置与帮助', icon: 'settings', items: [
      ...(desktop ? [leaf('settings', '工作台参数')] : []), leaf('help', '使用说明')]},
  ];
}

export function pageRoutes(categories) {
  const routes = [];
  function visit(items, keys = [], labels = []) {
    for (const item of items) {
      const route = {id: item.id, keys: [...keys, item.id], labels: [...labels, item.label]};
      if (item.items) visit(item.items, route.keys, route.labels);
      else routes.push(route);
    }
  }
  visit(categories);
  return routes;
}
