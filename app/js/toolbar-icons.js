// Full-color, beveled engineering symbols, drawn locally for the existing commands.
let sequence = 0;
export function toolbarIcon(name) {
  const id = `tool-art-${++sequence}`;
  const paint = key => `url(#${id}-${key})`;
  const cube = face => `<path d="M4 8 14 3 25 7 15 13Z" fill="${face === 'top' || face === 'iso' ? paint('cyan') : paint('paper')}"/><path d="M4 8 15 13v14L4 21Z" fill="${face === 'front' || face === 'iso' ? paint('cyan') : paint('paper')}"/><path d="m15 13 10-6v14l-10 6Z" fill="${face === 'side' || face === 'iso' ? paint('teal') : paint('steel')}"/><path d="m5 9 9 5v11" fill="none" stroke="#fff" opacity=".6"/>`;
  const art = {
    teaching: `<path d="M1 26h12l2 4H1Zm18 0h12v4H17Z" fill="${paint('navy')}"/><path d="m6 25-3-11 7-8 4 4-7 6 4 9Zm20 0 3-11-7-8-4 4 7 6-4 9Z" fill="${paint('steel')}"/><circle cx="5" cy="15" r="3" fill="${paint('blue')}"/><circle cx="27" cy="15" r="3" fill="${paint('blue')}"/><circle cx="11" cy="7" r="3" fill="${paint('blue')}"/><circle cx="21" cy="7" r="3" fill="${paint('blue')}"/><path d="M11 19h10m-3-3 4 3-4 3" fill="none" stroke="#23899a" stroke-width="2"/>`,
    xr: `<path d="M4 10 8 5h16l4 5" fill="none" stroke="#667f91" stroke-width="3"/><path d="M3 10h26v14l-7 3-6-5-6 5-7-3Z" fill="${paint('steel')}"/><path d="M5 12h22v9l-5 3-6-5-6 5-5-3Z" fill="${paint('navy')}"/><path d="M7 13h7v5H7Zm11 0h7v5h-7Z" fill="${paint('cyan')}"/><path d="M1 13h3v7H1Zm27 0h3v7h-3Z" fill="${paint('blue')}"/>`,
    'arm-config': `<path d="M3 26h17l3 4H2Z" fill="${paint('steel')}"/><path d="m8 25-4-11 10-9 5 5-10 7 5 8Z" fill="${paint('steel')}"/><circle cx="6" cy="14" r="4" fill="${paint('blue')}"/><circle cx="15" cy="7" r="4" fill="${paint('blue')}"/><path d="m21 14 4-1 2 3 4 1v5l-3 2-1 4-5 1-2-3-4-1v-5l3-2Z" fill="${paint('cyan')}"/><circle cx="24" cy="21" r="3" fill="${paint('paper')}"/>`,
    new: `<path d="M7 3h13l6 6v20H7Z" fill="${paint('paper')}"/><path d="M20 3v7h6" fill="${paint('steel')}"/><path d="M4 15h12v5H4zM8 11h5v13H8z" fill="${paint('green')}" stroke="#37723b"/>`,
    open: `<path d="m3 8 10-2 4 4 12-1-2 18-23 1Z" fill="${paint('blue')}"/><path d="m3 14 23-3-4 17-19-1Z" fill="${paint('navy')}"/><path d="m5 15 18-2" stroke="#b3e5ff"/>`,
    save: `<path d="M4 3h21l4 4v22H4Z" fill="${paint('navy')}"/><path d="M9 3h14v10H9Z" fill="${paint('steel')}"/><path d="M18 4h4v7h-4Z" fill="#31506c"/><path d="M8 18h17v11H8Z" fill="${paint('paper')}"/><path d="M11 21h11m-11 4h11" stroke="#8396a8"/>`,
    undo: `<path d="M12 8h7a10 10 0 0 1 0 20h-8v-5h8a5 5 0 0 0 0-10h-7v6L2 10 12 2Z" fill="${paint('cyan')}" stroke="#397988"/><path d="M13 10h6a8 8 0 0 1 7 4" fill="none" stroke="#e1ffff" opacity=".75"/>`,
    redo: `<g transform="translate(32 0) scale(-1 1)"><path d="M12 8h7a10 10 0 0 1 0 20h-8v-5h8a5 5 0 0 0 0-10h-7v6L2 10 12 2Z" fill="${paint('steel')}" stroke="#677d8c"/><path d="M13 10h6a8 8 0 0 1 7 4" fill="none" stroke="#fff" opacity=".8"/></g>`,
    iso: cube('iso'), front: cube('front'), side: cube('side'), top: cube('top'),
    fit: `<path d="M3 12V3h9L9 6l5 5-3 3-5-5Zm17-9h9v9l-3-3-5 5-3-3 5-5ZM3 20v9h9l-3-3 5-5-3-3-5 5Zm26 0v9h-9l3-3-5-5 3-3 5 5Z" fill="${paint('blue')}"/><rect x="13" y="13" width="6" height="6" fill="${paint('paper')}"/>`,
    grid: `<path d="m2 22 12-16 16 6-12 17Z" fill="${paint('steel')}"/><path d="m6 17 16 6M10 12l16 6M18 8 6 24M24 10 12 27" stroke="#526f87"/><path d="m3 21 14 6" stroke="#fff"/>`,
    axes: `<path d="M14 21V5" stroke="#3878c2" stroke-width="4"/><path d="m9 8 5-6 5 6Z" fill="${paint('blue')}"/><path d="m14 21 12 5" stroke="#c44134" stroke-width="4"/><path d="m23 20 7 8-10 1Z" fill="${paint('red')}"/><path d="M14 21 4 26" stroke="#348747" stroke-width="4"/><path d="m8 20-7 9 11-1Z" fill="${paint('green')}"/>`,
    robot: `<path d="M5 25h17l4 5H3Z" fill="${paint('navy')}"/><path d="m10 25-4-11 10-9 5 5-10 7 5 8Z" fill="${paint('steel')}"/><path d="m20 9 8 4-2 6-5-2 2-3-5-2Z" fill="${paint('steel')}"/><circle cx="8" cy="15" r="4" fill="${paint('blue')}"/><circle cx="17" cy="7" r="4" fill="${paint('blue')}"/><circle cx="8" cy="15" r="1.4" fill="#d9ebfa"/>`,
    target: `<ellipse cx="16" cy="18" rx="12" ry="10" fill="${paint('green')}" stroke="#3a713d"/><ellipse cx="16" cy="18" rx="7" ry="6" fill="none" stroke="#e7f8cb" stroke-width="2"/><path d="M16 3v24M3 18h26" stroke="#436f3a" stroke-width="1.5"/><circle cx="16" cy="18" r="2.5" fill="#f8f7bc"/>`,
    gripper: `<path d="M11 3h11v9H11Z" fill="${paint('blue')}"/><path d="M14 12h5v5h-5Z" fill="${paint('steel')}"/><path d="M5 16h23v5h-4v9h-7v-4h3v-5h-8v5h3v4H8v-9H5Z" fill="${paint('steel')}"/>`,
    move: `<path d="M14 12V5" stroke="#329049" stroke-width="3"/><path d="m10 7 4-5 4 5Z" fill="${paint('green')}"/><path d="M14 14H4m10 0h12m-12 0v13" stroke="#3b8eb4" stroke-width="3"/><path d="m7 10-5 4 5 4m16-8 6 4-6 4m-13 6 4 5 4-5" fill="${paint('blue')}"/><path d="m17 10 9 10-5 1 2 6-3 1-3-6-4 3Z" fill="${paint('paper')}" stroke="#4e5966"/>`,
    rotate: `<path d="M24 10a11 11 0 1 0 3 12l-5-2a6 6 0 1 1-2-6l-5 1 12 5 2-13Z" fill="${paint('red')}" stroke="#8d4337"/><path d="M10 4v10M5 9h10" stroke="#429240" stroke-width="3"/>`,
    home: `<path d="m3 15 13-12 13 12-3 3-10-9L6 18Z" fill="${paint('blue')}"/><path d="M7 17 16 9l9 8v12H7Z" fill="${paint('paper')}"/><path d="M13 20h7v9h-7Z" fill="${paint('navy')}"/>`,
    play: `<path d="M6 6 27 16 6 27Z" fill="${paint('blue')}" stroke="#3c789f"/><path d="m8 8 15 8-15-4Z" fill="#d1f3ff" stroke="none" opacity=".6"/>`,
    pause: `<rect x="6" y="6" width="7" height="21" rx="1" fill="${paint('blue')}"/><rect x="20" y="6" width="7" height="21" rx="1" fill="${paint('blue')}"/>`,
    reset: `<path d="M9 8a11 11 0 1 1-5 12l5-1a6 6 0 1 0 4-7l5 3-13 1V3Z" fill="${paint('cyan')}" stroke="#31788b"/>`,
    settings: `<path d="m13 3 7 0 1 5 5 2 4 5-3 6-5 2-2 7h-7l-2-5-5-2-3-6 3-6 5-2Z" fill="${paint('steel')}"/><circle cx="16" cy="17" r="6" fill="${paint('navy')}"/><circle cx="16" cy="17" r="3" fill="${paint('paper')}"/>`,
    list: `<path d="M8 3h18v26H8Z" fill="${paint('paper')}"/><path d="M13 9h10m-10 6h10m-10 6h10m-10 5h8" stroke="#6e8192"/><path d="M3 7h7v5H3Zm0 7h7v5H3Zm0 7h7v5H3Z" fill="${paint('blue')}"/>`,
    help: `<circle cx="16" cy="16" r="13" fill="${paint('blue')}" stroke="#315881"/><ellipse cx="13" cy="9" rx="8" ry="4" fill="#e6f5ff" opacity=".4" stroke="none"/><path d="M14 14h4v10h-4Z" fill="#fff" stroke="none"/><circle cx="16" cy="9" r="2" fill="#fff" stroke="none"/>`,
  };
  const colors = {paper:['#ffffff','#d8e1e8'],steel:['#eef4f8','#8295a7'],blue:['#a2def4','#22669b'],navy:['#7794b7','#152c4b'],cyan:['#a1e8e9','#2194a4'],teal:['#5fc6ce','#176576'],green:['#c7e99c','#4b9c44'],red:['#efb099','#bb392d']};
  const defs = Object.entries(colors).map(([key,[light,dark]]) => `<linearGradient id="${id}-${key}" x1="0" y1="0" x2=".7" y2="1"><stop stop-color="${light}"/><stop offset="1" stop-color="${dark}"/></linearGradient>`).join('');
  return `<svg class="engineering-icon" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><defs>${defs}</defs><g stroke="#506777" stroke-width=".9" stroke-linejoin="round" stroke-linecap="round">${art[name] || art.iso}</g></svg>`;
}
