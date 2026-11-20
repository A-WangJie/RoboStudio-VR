// One popover outside the scrolling toolbar; nested groups expand in place.
export function createFunctionMenu({open, current}) {
  const menu = document.createElement('div');
  menu.className = 'function-menu'; menu.hidden = true; menu.setAttribute('role', 'menu');
  document.body.append(menu);
  let owner;
  function close(focus = false) {
    menu.hidden = true; owner?.setAttribute('aria-expanded', 'false');
    if (focus) owner?.focus();
  }
  function expand(button, expanded, focus = false) {
    button.setAttribute('aria-expanded', String(expanded));
    const group = button.nextElementSibling;
    group.hidden = !expanded;
    if (focus && expanded) group.querySelector('button:not(:disabled)')?.focus();
  }
  function build(items, parent, keys) {
    for (const item of items) {
      const path = [...keys, item.id];
      const button = document.createElement('button'); button.type = 'button';
      button.dataset.shortcutRoute = path.join('/');
      button.setAttribute('role', 'menuitem');
      if (item.items) {
        const wrapper = document.createElement('div'); wrapper.className = 'function-branch'; wrapper.setAttribute('role', 'none');
        button.dataset.subcategory = item.id; button.className = 'function-subcategory';
        const label = document.createElement('span'); label.textContent = item.label;
        const arrow = document.createElement('span'); arrow.className = 'submenu-arrow'; arrow.textContent = '▸'; arrow.setAttribute('aria-hidden', 'true');
        button.append(label, arrow); button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-haspopup', 'menu');
        const group = document.createElement('div'); group.className = 'function-submenu'; group.hidden = true;
        group.id = `function-submenu-${path.join('-')}`; group.setAttribute('role', 'menu'); group.setAttribute('aria-label', item.label);
        button.setAttribute('aria-controls', group.id);
        wrapper.append(button, group); parent.append(wrapper); build(item.items, group, path);
        button.addEventListener('click', () => expand(button, group.hidden));
      } else {
        button.textContent = item.label; button.dataset.functionPage = item.id;
        button.dataset.functionRoute = path.join('/');
        button.setAttribute('aria-current', String(current().id === item.id && current().keys.join('/') === path.join('/')));
        button.addEventListener('click', () => {close(true); open(item.id, path);}); parent.append(button);
      }
    }
  }
  function show(button, category) {
    if (owner === button && !menu.hidden) {close(); return false;}
    close(); owner = button; menu.replaceChildren(); build(category.items, menu, [category.id]);
    menu.setAttribute('aria-label', category.label);
    const rect = button.getBoundingClientRect();
    menu.style.top = `${rect.bottom + 3}px`;
    menu.style.left = `${Math.max(4, Math.min(rect.left, innerWidth - 286))}px`;
    menu.style.maxHeight = `${Math.max(120, innerHeight - rect.bottom - 12)}px`;
    menu.hidden = false; button.setAttribute('aria-expanded', 'true');
    menu.querySelector('button:not(:disabled)')?.focus(); return true;
  }
  menu.addEventListener('keydown', event => {
    const buttons = [...menu.querySelectorAll('button:not(:disabled)')].filter(button => !button.closest('[hidden]'));
    const active = document.activeElement, index = buttons.indexOf(active);
    if (event.key === 'Escape') {event.preventDefault(); close(true);}
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault(); (event.key === 'Home' ? buttons[0] : buttons.at(-1))?.focus();
    } else if (event.key === 'ArrowRight' && active.matches('[data-subcategory]')) {
      event.preventDefault(); expand(active, true, true);
    } else if (event.key === 'ArrowLeft') {
      const branch = active.matches('[data-subcategory][aria-expanded=true]') ? active : active.closest('.function-submenu')?.previousElementSibling;
      if (branch) {event.preventDefault(); expand(branch, false); branch.focus();}
    } else if (event.key === 'Tab') close();
  });
  document.addEventListener('pointerdown', event => {
    if (!menu.contains(event.target) && !event.target.closest('.function-category, .shortcut-context-menu')) close();
  });
  window.addEventListener('resize', () => close());
  return {menu, show, close};
}
