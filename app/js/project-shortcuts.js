import { functionCategories } from './navigation.js';

const STORAGE_KEY = 'robostudio.project-shortcuts.v1';
const entries = new Map();
function index(items, keys = []) {
  for (const item of items) {
    const path = [...keys, item.id];
    entries.set(path.join('/'), item);
    if (item.items) index(item.items, path);
  }
}
index(functionCategories());
let hidden = new Set();
let saving = Promise.resolve();
function applySaved(value) {
  hidden = new Set(Array.isArray(value) ? value.filter(route => entries.has(route)) : []);
}
function read() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
    applySaved(value);
  } catch {hidden = new Set();}
}
read();

export async function loadShortcutPreferences() {
  if (!window.s1Desktop?.projectShortcuts) return;
  // Electron's local HTTP port changes at startup, so use a stable config file.
  try {applySaved(await window.s1Desktop.projectShortcuts());}
  catch (error) {console.warn('读取快捷目标栏设置失败，使用当前显示设置：', error);}
}

export function shortcutVisible(route) {
  const keys = route.split('/');
  return keys.every((_, i) => !hidden.has(keys.slice(0, i + 1).join('/')));
}

function setVisible(route, visible) {
  if (!entries.has(route)) return;
  if (visible) {
    const keys = route.split('/');
    keys.forEach((_, i) => hidden.delete(keys.slice(0, i + 1).join('/')));
  } else hidden.add(route);
  try {localStorage.setItem(STORAGE_KEY, JSON.stringify([...hidden]));} catch { /* Keep the current session's choice if storage is unavailable. */ }
  if (window.s1Desktop?.saveProjectShortcuts) {
    const preferences = [...hidden];
    saving = saving.then(() => window.s1Desktop.saveProjectShortcuts(preferences)).catch(error => {
      console.error('保存快捷目标栏设置失败：', error);
      window.dispatchEvent(new CustomEvent('s1:notice', {detail: {text: '快捷目标栏已更新，但保存失败：' + error.message, error: true}}));
    });
  }
  window.dispatchEvent(new CustomEvent('s1:shortcuts-changed', {detail: {route, visible}}));
}

// Only navigation entries opt in; right clicks never invoke motion commands.
export function installShortcutMenu() {
  const menu = document.createElement('div'); menu.id = 'shortcut-context-menu';
  menu.className = 'shortcut-context-menu'; menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', '快捷目标栏管理'); menu.hidden = true;
  const label = document.createElement('div'); label.className = 'shortcut-context-label';
  const action = document.createElement('button'); action.type = 'button'; action.setAttribute('role', 'menuitem');
  menu.append(label, action); document.body.append(menu);
  let owner, route;
  function close(restore = false) {
    menu.hidden = true;
    if (restore && owner?.isConnected && !owner.closest('[hidden]')) owner.focus({preventScroll: true});
  }
  function show(event, target) {
    const key = target.dataset.shortcutRoute;
    if (!entries.has(key)) return;
    event.preventDefault(); event.stopPropagation();
    owner = target; route = key;
    label.textContent = entries.get(key).label;
    action.textContent = shortcutVisible(key) ? '移出快捷目标栏（项目树）' : '添加到快捷目标栏（项目树）';
    action.dataset.shortcutAction = shortcutVisible(key) ? 'remove' : 'add';
    menu.hidden = false;
    const rect = target.getBoundingClientRect();
    const keyboard = event.type === 'keydown' || (!event.clientX && !event.clientY);
    const x = keyboard ? rect.left : event.clientX, y = keyboard ? rect.bottom : event.clientY;
    menu.style.left = `${Math.max(4, Math.min(x, innerWidth - menu.offsetWidth - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(y, innerHeight - menu.offsetHeight - 4))}px`;
    action.focus({preventScroll: true});
  }
  action.addEventListener('click', () => {
    setVisible(route, !shortcutVisible(route));
    // A removed tree item is hidden; focus its visible project container instead.
    if (owner?.closest('[hidden]')) owner = document.querySelector('[data-node="project-file"]');
    close(true);
  });
  document.addEventListener('contextmenu', event => {
    const target = event.target.closest('[data-shortcut-route]');
    if (target) show(event, target);
    else close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)) {
      const target = event.target.closest('[data-shortcut-route]');
      if (target) {event.stopImmediatePropagation(); show(event, target);}
    } else if (!menu.hidden && event.key === 'Escape') {
      event.preventDefault(); event.stopImmediatePropagation(); close(true);
    } else if (!menu.hidden && event.key === 'Tab') close();
  }, true);
  document.addEventListener('pointerdown', event => {if (!menu.contains(event.target)) close();}, true);
  document.addEventListener('scroll', () => close(), true);
  window.addEventListener('resize', () => close());
  window.addEventListener('blur', () => close());
  window.addEventListener('storage', event => {
    if (event.key === STORAGE_KEY || event.key === null) {
      read(); close(); window.dispatchEvent(new Event('s1:shortcuts-changed'));
    }
  });
}
