// Builds the one classroom frame (header, teacher, board card, speaker rail, dock) so every screen shares it.
// A page only says what changes: the board content, who is speaking, what the teacher says and what the dock shows.
const IC = {
  list: '<path d="M4 5h16M4 12h16M4 19h10"/>', repeat: '<path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v5h5"/>', chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  sound: '<path d="M4 9v6h4l5 4V5L8 9zM16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"/>', soundoff: '<path d="M4 9v6h4l5 4V5L8 9zM16 9l6 6M22 9l-6 6"/>',
  expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>', mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
  micoff: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M3 3l18 18"/>', keyboard: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10"/>',
  hand: '<path d="M9 11V5.5a1.5 1.5 0 0 1 3 0V10m0-1V4.5a1.5 1.5 0 0 1 3 0V10m0-3a1.5 1.5 0 0 1 3 0v7a7 7 0 0 1-7 7h-.5a6 6 0 0 1-5-3L3 13.5a1.5 1.5 0 0 1 2.4-1.7L9 15"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', arrow: '<path d="M5 12h14m-5-5l5 5-5 5"/>', pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>', book: '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
  bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>', ear: '<path d="M6 9a6 6 0 1 1 11 3.3c-1.2 1.6-2.5 2.2-2.5 4.2a3 3 0 0 1-5.6 1.5M9.5 9.5a2.5 2.5 0 0 1 5 0"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', redo: '<path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v5h-5"/>',
};
const ic = (n, s) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"${s ? ` style="width:${s}px;height:${s}px"` : ''}>${IC[n] || ''}</svg>`;
const TINT = ['#FFE3C2', '#D3EBFF', '#D5F2E4', '#FBD9DC', '#E6DEFB', '#FFF0B8'];
const NAMES = ['Diya', 'Kabir', 'Meera', 'Rohan', 'Aarav', 'Ishaan', 'Anaya', 'Vivaan', 'Saanvi', 'Reyansh', 'Myra', 'Arjun', 'Kiara', 'Dev', 'Tara', 'Neel', 'Zoya', 'Yash', 'Pihu', 'Om'];
const av = (name, s = 40, extra = '') => `<span class="av" style="--s:${s}px;--c:${extra || TINT[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % TINT.length]}">${name[0]}</span>`;
const ribbon = (n = 14, seed = 1, cls = '') => `<span class="ribbon ${cls}">${Array.from({ length: n }, (_, k) => `<span style="--h:${(28 + 62 * Math.abs(Math.sin(k * 0.7 + seed) * Math.cos(k * 0.23 + seed * 2))).toFixed(0)}"></span>`).join('')}</span>`;

const MOUTH = { idle: 'M180 256Q200 259 220 256Q200 266 180 256Z', speaking: 'M178 253Q200 250 222 253Q214 281 200 282Q186 281 178 253Z' };
const AVATAR = (state) => `<svg class="avatar" viewBox="0 0 400 520" role="img" aria-label="Teacher"><defs>
  <linearGradient id="gBlazer" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7189EA"/><stop offset="1" stop-color="#4A61C6"/></linearGradient>
  <linearGradient id="gHair" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4B2D1E"/><stop offset="1" stop-color="#2C1810"/></linearGradient>
  <radialGradient id="gSkin" cx=".45" cy=".38" r=".75"><stop offset="0" stop-color="#F3C49E"/><stop offset="1" stop-color="#DFA27A"/></radialGradient>
  <clipPath id="cEyeL"><ellipse cx="166" cy="202" rx="15" ry="16"/></clipPath><clipPath id="cEyeR"><ellipse cx="234" cy="202" rx="15" ry="16"/></clipPath></defs>
  <path fill="url(#gHair)" d="M200 70C120 70 96 140 100 220C104 300 92 360 104 430L296 430C308 360 296 300 300 220C304 140 280 70 200 70Z"/>
  <path fill="#D6956C" d="M178 280L222 280L226 345L174 345Z"/><path fill="#FFFFFF" d="M158 340L200 440L242 340L226 330L174 330Z"/>
  <path fill="none" stroke="#E9C46A" stroke-width="2.5" d="M178 334Q200 372 222 334"/><circle cx="200" cy="366" r="6" fill="#FFD44D"/>
  <path fill="url(#gBlazer)" d="M30 520C40 420 90 360 158 340L200 440L242 340C310 360 360 420 370 520Z"/>
  <path fill="#3D52B5" d="M158 340L200 440L186 446L144 352Z"/><path fill="#3D52B5" d="M242 340L200 440L214 446L256 352Z"/>
  <path fill="url(#gHair)" d="M104 290C94 360 112 420 146 452C132 400 130 340 136 286Z"/><path fill="url(#gHair)" d="M296 290C306 360 288 420 254 452C268 400 270 340 264 286Z"/>
  <ellipse cx="123" cy="208" rx="12" ry="18" fill="#DFA27A"/><ellipse cx="277" cy="208" rx="12" ry="18" fill="#DFA27A"/>
  <circle cx="122" cy="232" r="4.5" fill="#FFD44D"/><circle cx="278" cy="232" r="4.5" fill="#FFD44D"/>
  <path fill="url(#gSkin)" d="M200 104C252 104 280 145 280 200C280 258 246 296 200 296C154 296 120 258 120 200C120 145 148 104 200 104Z"/>
  <path fill="url(#gHair)" d="M117 206C106 128 150 82 206 80C264 80 298 126 285 206C276 160 254 134 226 126C206 156 166 172 123 182Z"/>
  <path class="brow" d="M146 174Q164 161 184 169"/><path class="brow" d="M216 169Q236 161 254 174"/>
  <ellipse cx="166" cy="202" rx="15" ry="16" fill="#FFFFFF"/><ellipse cx="234" cy="202" rx="15" ry="16" fill="#FFFFFF"/>
  <g clip-path="url(#cEyeL)"><circle cx="167" cy="205" r="10" fill="#5A3420"/><circle cx="167" cy="205" r="5" fill="#1C0F08"/><circle cx="171" cy="200" r="3.2" fill="#FFFFFF"/></g>
  <g clip-path="url(#cEyeR)"><circle cx="235" cy="205" r="10" fill="#5A3420"/><circle cx="235" cy="205" r="5" fill="#1C0F08"/><circle cx="239" cy="200" r="3.2" fill="#FFFFFF"/></g>
  <path class="lash" d="M150 197Q166 182 182 195"/><path class="lash" d="M218 195Q234 182 250 197"/>
  <path fill="none" stroke="#C47F5B" stroke-width="3.5" stroke-linecap="round" d="M199 216Q194 234 204 237"/>
  <circle cx="148" cy="244" r="14" fill="#F08A8A" opacity=".3"/><circle cx="252" cy="244" r="14" fill="#F08A8A" opacity=".3"/>
  <path fill="#A23B4A" d="${MOUTH[state === 'speaking' ? 'speaking' : 'idle']}"/></svg>`;

function rail(r = {}) {
  const parts = [];
  if (r.timer) parts.push(`<div class="rcard timer"><div class="ring" style="--p:${r.timer.p}"><b>${r.timer.text}</b></div><p>Time left to answer</p></div>`);
  if (r.now) parts.push(`<div class="rcard"><h3>Speaking now</h3><div class="who">${av(r.now.role === 'teacher' ? 'Asha' : r.now.name, 46, r.now.role === 'teacher' ? '#FFD44D' : '')}${r.now.name}<span class="chip ${r.now.tone || ''}">${r.now.state}</span></div></div>`);
  if (r.queue) parts.push(`<div class="rcard"><h3>Hands up</h3>${r.queue.length ? r.queue.slice(0, 3).map((n, i) => `<div class="q"><span class="n">${i + 1}</span>${n}</div>`).join('') : '<div style="color:var(--on-dark-soft);font-size:20px">No hands up</div>'}</div>`);
  const here = r.here ?? 18;
  parts.push(`<div class="rcard"><h3>Class</h3>${r.score ? `<div class="score">${r.score[0]}<small>of ${r.score[1]} right</small></div>` : ''}<div class="stack">${NAMES.slice(0, 5).map((n) => av(n, 32)).join('')}<span class="more">${here} of 20 here</span></div></div>`);
  return parts.join('');
}

function mount(c) {
  const steps = c.step ? `<div class="steps">${Array.from({ length: c.step.total }, (_, i) => `<i class="${i + 1 < c.step.n ? 'done' : i + 1 === c.step.n ? 'now' : ''}"></i>`).join('')}<span>${c.step.label || `Question ${c.step.n} of ${c.step.total}`}</span></div>` : '<div class="steps"></div>';
  const t = c.teacher || {};
  const d = c.dock || {};
  document.body.innerHTML = `<div class="stage">
    <header class="top"><span class="mark">Aa</span><div class="cls">${c.cls || 'Class 8 · English'}<small>${c.title || ''}</small></div>${steps}
      <div class="tools"><button class="tool">${ic('list')}</button><button class="tool">${ic('repeat')}</button><button class="tool ${c.drawer ? 'on' : ''}">${ic('chat')}</button>
      <button class="tool">${ic('sound')}</button><button class="tool">${ic('expand')}</button><span class="clock">9:28 pm</span></div></header>
    <div class="body">
      <aside class="tcol ${t.state === 'paused' ? 'paused' : ''}"><div class="spot">${t.state === 'thinking' ? '<div class="thinking"><i></i><i></i><i></i></div>' : ''}${AVATAR(t.state)}</div>
        <div class="tname ${t.state === 'paused' ? 'paused' : ''}">${av('Asha', 38, '#FFD44D')}Ms. Asha${t.state === 'paused' ? '<span class="chip chalk">Paused</span>' : ribbon(10, 2, t.state === 'speaking' ? '' : 'calm')}</div>
        ${t.say ? `<div class="bubble">${t.say}</div>` : ''}</aside>
      <main class="board ${c.paused ? 'paused' : ''}">${c.paused || ''}${c.board}</main>
      <aside class="rail">${rail(c.rail)}</aside>
    </div>
    <footer class="dock"><div class="status">${ic(d.icon || 'ear', 30)}<span>${d.status || ''}</span>${d.wave ? ribbon(26, 3, d.wave === 'big' ? '' : 'calm') : ''}</div>
      ${d.type ? `<button class="btn">${ic('keyboard')}Type instead</button>` : ''}${d.hand ? `<button class="btn">${ic('hand')}Hands up</button>` : ''}${d.next ? `<button class="btn chalk">${d.next}${ic('arrow')}</button>` : ''}
      <button class="mic ${d.mic || ''}">${ic(d.mic === 'off' ? 'micoff' : 'mic')}</button></footer>
    ${c.overlay ? `<div class="overlay">${c.overlay}</div>` : ''}${c.drawer || ''}</div>`;
}
window.CR = { mount, ic, av, ribbon, NAMES, TINT };
