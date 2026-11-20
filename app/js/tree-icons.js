// Compact CAD-style object symbols, sized for a 16px feature tree.
const symbols = {
  folder: '<path d="M1 4V2h6l2 2h6v10H1Z" fill="#c79e50"/><path d="M1 6h14l-2 8H1Z" fill="#efd092"/><path d="M2 7h11" stroke="#fff0c3"/>',
  file: '<path d="M3 1h7l4 4v10H3Z" fill="#f1f5f8"/><path d="M10 1v4h4" fill="#b4cbdc"/><path d="M5 8h7M5 11h7" fill="none" stroke="#6c8ca3"/>',
  new: '<path d="m8 1 4 2-4 2-4-2Z" fill="#ffe09a"/><path d="M4 3v5l4 2V5Z" fill="#c89537"/><path d="m8 5 4-2v5l-4 2Z" fill="#e9b950"/><path d="m4 7 4 2-4 2-4-2Z" fill="#ffe09a"/><path d="M0 9v4l4 2v-4Z" fill="#c89537"/><path d="m4 11 4-2v4l-4 2Z" fill="#e9b950"/><path d="m12 7 4 2-4 2-4-2Z" fill="#ffe09a"/><path d="M8 9v4l4 2v-4Z" fill="#c89537"/><path d="m12 11 4-2v4l-4 2Z" fill="#e9b950"/>',
  robot: '<path d="m7 2 6 3-6 3-6-3Z" fill="#e0e8ec"/><path d="M1 5v7l6 3V8Z" fill="#8d9eaa"/><path d="m7 8 6-3v7l-6 3Z" fill="#b5c3cb"/><path d="m10 7 5 2-5 2-4-2Z" fill="#bdd49c"/><path d="M6 9v4l4 2v-4Z" fill="#6d914e"/><path d="m10 11 5-2v4l-5 2Z" fill="#91b56c"/>',
  axes: '<g fill="none" stroke-width="1.4"><path d="M7 10V1m-2 2 2-2 2 2" stroke="#28649b"/><path d="m7 10 8 3m-2-3 2 3-3 1" stroke="#b44238"/><path d="m7 10-6 4m0-3v3h3" stroke="#43864c"/></g><rect x="5.5" y="8.5" width="3" height="3" fill="#f4f4ed" stroke="#596b74"/>',
  'joint-group': '<path d="M1 4V2h6l2 2h6v10H1Z" fill="#c79e50"/><path d="M1 6h14l-2 8H1Z" fill="#efd092"/><path d="M2 7h11" stroke="#fff0c3"/><circle cx="10.5" cy="10.5" r="3.6" fill="#8aadb9" stroke="#4e7182"/><circle cx="10.5" cy="10.5" r="1.4" fill="#e9eff0"/>',
  joint: '<path d="m3 4 5-2 5 2-5 3Z" fill="#cbdce3"/><path d="M3 4v8l5 3V7Z" fill="#829fac"/><path d="m8 7 5-3v8l-5 3Z" fill="#aec5cf"/><ellipse cx="8" cy="4" rx="3" ry="1.4" fill="#e4ecee"/><path d="M2 9C0 5 4 1 8 1m-3 0h3v3" fill="none" stroke="#396b9a" stroke-width="1.2"/>',
  gripper: '<path d="M5 1h6v4H5Z" fill="#a9bac4"/><path d="M7 5h2v3H7Z" fill="#6f828d"/><path d="M2 7h12v3h-2v5H9v-2h1v-3H6v3h1v2H4v-5H2Z" fill="#d2b776"/><path d="M3 8h10" stroke="#fff2c4"/>',
  target: '<circle cx="8" cy="8" r="5" fill="#e2eddb" stroke="#4c7950"/><circle cx="8" cy="8" r="2" fill="#6a9c63"/><path d="M8 0v5m0 6v5M0 8h5m6 0h5" stroke="#4c7950" fill="none"/>',
  grid: '<path d="m1 6 9-4 5 8-9 4Z" fill="#e8c17a" fill-opacity=".5" stroke="#a47b35"/><path d="m4 5 5 8M7 3l5 9M3 9l9-4m-7 7 9-4" fill="none" stroke="#a47b35" stroke-width=".65"/><path d="m1 6 5 8" stroke="#f5dfb1"/>',
};

export function icon(name) {
  return `<svg viewBox="-1 -1 18 18" aria-hidden="true" focusable="false"><g stroke="#596670" stroke-width=".55" stroke-linejoin="round">${symbols[name] || symbols.robot}</g></svg>`;
}
