// Shared vector symbols for existing workbench commands and project objects.
const paths = {
  new: '<path d="M5 3h9l5 5v13H5z"/><path d="M14 3v6h5M9 14h6m-3-3v6"/>',
  open: '<path class="icon-face" d="M3 8h7l2 3h9l-3 9H3z"/><path d="M3 11V5h7l2 3h8v3"/>',
  save: '<path class="icon-face" d="M4 3h13l4 4v14H3V3z"/><path d="M7 3v6h9V3M7 21v-8h10v8M13 4v3"/>',
  fit: '<path d="M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6"/><path class="icon-face" d="M8 8h8v8H8z"/>',
  iso: '<path class="icon-face" d="m12 2 9 5v10l-9 5-9-5V7z"/><path d="m3 7 9 5 9-5M12 12v10"/>',
  front: '<path d="M4 7h13v14H4zM4 7l4-4h13v14l-4 4M17 7l4-4"/><path class="icon-solid" d="M6 9h9v10H6z"/>',
  side: '<path d="M3 7h13v14H3zM3 7l5-4h13v14l-5 4M16 7l5-4"/><path class="icon-solid" d="m17 8 3-3v11l-3 3z"/>',
  top: '<path d="M3 8h13v13H3zM3 8l5-5h13v13l-5 5M16 8l5-5"/><path class="icon-solid" d="m6 7 3-3h10l-3 3z"/>',
  grid: '<path d="M3 4h18v16H3zM3 9h18M3 15h18M9 4v16M15 4v16"/>',
  axes: '<path stroke="#e68c88" d="m10 14 11 5m-4-1 4 1-2-4"/><path stroke="#7ac6a0" d="m10 14-7 5m1-4-1 4 4-1"/><path stroke="#83b8f0" d="M10 14V2m-3 4 3-4 3 4"/>',
  move: '<path d="M12 2v20M2 12h20M8 6l4-4 4 4M8 18l4 4 4-4M6 8l-4 4 4 4m12-8 4 4-4 4"/>',
  rotate: '<path d="M20 9a8 8 0 1 0 0 6M20 3v6h-6"/><circle cx="12" cy="12" r="2"/>',
  robot: '<path d="M4 21h12l-2-4H6zM8 17l-3-7 8-6 5 5-4 3-3-4-3 3 3 6M18 9l3 2-2 4-3-2"/><circle cx="6" cy="10" r="2"/><circle cx="13" cy="5" r="2"/>',
  joint: '<circle cx="12" cy="12" r="7"/><circle class="icon-face" cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
  gripper: '<path d="M8 3h8v5H8zM12 8v4M5 12h14M5 12v8h4v-5m10-3v8h-4v-5"/>',
  target: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/><path d="M12 1v5m0 12v5M1 12h5m12 0h5"/>',
  home: '<path d="m3 11 9-8 9 8M5 9v12h14V9M10 21v-7h4v7"/>',
  play: '<path class="icon-face" d="m7 3 14 9-14 9z"/>',
  pause: '<path class="icon-solid" d="M6 4h4v16H6zM15 4h4v16h-4z"/>',
  reset: '<path d="M4 9a8 8 0 1 1 0 6M4 3v6h6"/><path class="icon-face" d="M9 9h6v6H9z"/>',
  settings: '<path d="M9 3h6l1 4 4 2v6l-4 2-1 4H9l-1-4-4-2V9l4-2z"/><circle cx="12" cy="12" r="3"/>',
  list: '<path d="M8 5h13M8 12h13M8 19h13M3 5h1M3 12h1M3 19h1"/>',
  help: '<circle class="icon-face" cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
};

export function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths[name] || paths.iso}</svg>`;
}
