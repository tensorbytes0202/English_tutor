// Shared bits for the mockups: icons, voice ribbons, avatar colours and the admin sidebar.
const ICONS = {
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  home: '<path d="M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
  dash: '<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>',
  live: '<circle cx="12" cy="12" r="2.2"/><path d="M8 8a5.6 5.6 0 0 0 0 8M16 8a5.6 5.6 0 0 1 0 8M5 5a9.8 9.8 0 0 0 0 14M19 5a9.8 9.8 0 0 1 0 14"/>',
  coin: '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.4c-.5-.8-1.4-1.2-2.5-1.2-1.5 0-2.6.8-2.6 2 0 2.6 5.4 1.3 5.4 4 0 1.2-1.1 2-2.8 2-1.2 0-2.2-.5-2.8-1.4M12 6v2m0 8v2"/>',
  book: '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0M16 5a3.2 3.2 0 0 1 0 6M18 14.5a6 6 0 0 1 3 5.5"/>',
  chart: '<path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  hand: '<path d="M9 11V5.5a1.5 1.5 0 0 1 3 0V10m0-1V4.5a1.5 1.5 0 0 1 3 0V10m0-3a1.5 1.5 0 0 1 3 0v7a7 7 0 0 1-7 7h-.5a6 6 0 0 1-5-3L3 13.5a1.5 1.5 0 0 1 2.4-1.7L9 15"/>',
  pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
  play: '<path d="M7 4l13 8-13 8z"/>',
  mute: '<path d="M4 9v6h4l5 4V5L8 9zM17 9l4 6M21 9l-4 6"/>',
  bell: '<path d="M6 17V11a6 6 0 0 1 12 0v6l2 2H4zM10 21h4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  alert: '<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  down: '<path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
  sound: '<path d="M4 9v6h4l5 4V5L8 9zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
  edit: '<path d="M4 20l4-1 11-11-3-3L5 16zM14 6l3 3"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10"/>',
  arrow: '<path d="M5 12h14m-5-5l5 5-5 5"/>',
};
const icon = (n) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;
document.querySelectorAll('[data-i]').forEach((el) => el.insertAdjacentHTML('afterbegin', icon(el.dataset.i)));

// A ribbon is a row of bars. The heights come from a fixed formula so every screenshot looks the same.
document.querySelectorAll('.ribbon').forEach((el) => {
  const n = +(el.dataset.n || 24), seed = +(el.dataset.seed || 1);
  el.innerHTML = Array.from({ length: n }, (_, k) => {
    const h = 28 + 62 * Math.abs(Math.sin(k * 0.7 + seed) * Math.cos(k * 0.23 + seed * 2));
    return `<span style="--h:${h.toFixed(0)};--d:${((k * 0.13) % 1).toFixed(2)}"></span>`;
  }).join('');
});

const TINTS = ['#FFE3C2', '#D3EBFF', '#D5F2E4', '#FBD9DC', '#E6DEFB', '#FFF0B8'];
document.querySelectorAll('.av[data-n]').forEach((el) => {
  const name = el.dataset.n;
  if (!el.hasAttribute('data-keep')) el.style.setProperty('--c', TINTS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % TINTS.length]);
  el.textContent = name[0];
});

// Admin sidebar, built from <body data-page="...">.
const NAV = [['dash', 'Overview', 'index'], ['live', 'Live classes', 'live', '3'], ['book', 'Lessons', 'lessons'],
  ['users', 'Students & classes', 'students'], ['chart', 'Reports', 'reports'], ['coin', 'Cost & usage', 'cost'], ['shield', 'Safety & settings', 'settings']];
const side = document.querySelector('.side');
if (side) {
  side.innerHTML = `<div class="brand"><span class="mark"><span class="ribbon" data-n="5" data-seed="2"></span></span>
      <span>Open Minds Tutor<small>Admin</small></span></div>` +
    NAV.map(([i, label, page, badge]) => `<a href="${page}.html" class="${document.body.dataset.page === page ? 'on' : ''}">${icon(i)}${label}${badge ? `<span class="chip sun">${badge}</span>` : ''}</a>`).join('') +
    `<div class="sep"></div><div class="me"><span class="av" data-n="Kapoor" style="--s:38px"></span><span>Mrs. Kapoor<small>School admin</small></span></div>`;
  side.querySelectorAll('.ribbon').forEach((el) => { el.innerHTML = Array.from({ length: 5 }, (_, k) => `<span style="--h:${[40, 85, 60, 100, 50][k]}"></span>`).join(''); });
  side.querySelectorAll('.av[data-n]').forEach((el) => { el.style.setProperty('--c', '#FFE3C2'); el.textContent = el.dataset.n[0]; });
}
