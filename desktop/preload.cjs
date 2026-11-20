const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('s1Desktop', Object.freeze({
  menus: () => ipcRenderer.invoke('s1:menus'),
  popupMenu: (index, position) => ipcRenderer.invoke('s1:menu-popup', index, position),
  info: () => ipcRenderer.invoke('s1:info'),
  settings: () => ipcRenderer.invoke('s1:settings-read'),
  saveSettings: settings => ipcRenderer.invoke('s1:settings-save', settings),
  projectShortcuts: () => ipcRenderer.invoke('s1:project-shortcuts-read'),
  saveProjectShortcuts: routes => ipcRenderer.invoke('s1:project-shortcuts-save', routes),
  armConfig: () => ipcRenderer.invoke('s1:arm-config-read'),
  saveArmConfig: config => ipcRenderer.invoke('s1:arm-config-save', config),
  fileAction: action => ipcRenderer.invoke('s1:file-action', action),
  editAction: action => ipcRenderer.invoke('s1:edit-action', action),
  windowAction: action => ipcRenderer.invoke('s1:window-action', action),
  windowState: () => ipcRenderer.invoke('s1:window-state'),
  onWindowState: callback => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('s1:window-state', listener);
    return () => ipcRenderer.removeListener('s1:window-state', listener);
  },
  onAction: callback => {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on('s1:action', listener);
    return () => ipcRenderer.removeListener('s1:action', listener);
  },
  completeAction: (id, result) => ipcRenderer.send('s1:action-result', {id, result}),
}));
