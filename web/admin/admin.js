// Shared by every admin page: API calls, small DOM helpers (text is never parsed as HTML), the sidebar, forms and charts.
const SVG = 'http://www.w3.org/2000/svg';
const ICONS = { // one SVG path each
  classes: 'M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4',
  users: 'M5.8 8a3.2 3.2 0 1 0 6.4 0 3.2 3.2 0 1 0-6.4 0M3 20a6 6 0 0 1 12 0M16 5a3.2 3.2 0 0 1 0 6M18 14.5a6 6 0 0 1 3 5.5',
  board: 'M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM8 20h8M12 16v4',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13', plus: 'M12 5v14M5 12h14',
  out: 'M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 8l4 4-4 4M20 12H9',
};
const NAV = [['classes', 'Classes', 'index.html'], ['calendar', 'Schedule', 'schedule.html'], ['users', 'Students', 'students.html']];
const TINTS = ['#FFE3C2', '#D3EBFF', '#D5F2E4', '#FBD9DC', '#E6DEFB', '#FFF0B8'];

function build(node, props, kids) {
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...kids.flat(Infinity).filter((kid) => kid != null && kid !== false));
  return node;
}
export const el = (tag, props = {}, ...kids) => build(document.createElement(tag), props, kids);
const svg = (tag, props = {}, ...kids) => build(document.createElementNS(SVG, tag), props, kids);

export const icon = (name) => svg('svg', { class: 'i', viewBox: '0 0 24 24', 'aria-hidden': 'true' }, svg('path', { d: ICONS[name] }));

// ---- data ----
const human = (field) => String(field).replace(/_/g, ' ');
const describe = (detail) => (Array.isArray(detail)
  ? detail.map((d) => (['missing', 'string_too_short'].includes(d.type) ? `Enter ${human(d.loc.at(-1))}.` : `${human(d.loc.at(-1))}: ${d.msg}.`)).join(' ')
  : detail);

const toLogin = () => { location.href = `/login.html?next=${encodeURIComponent(location.pathname + location.search)}`; };

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api/admin${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body && JSON.stringify(body) });
  if (res.status === 401) { toLogin(); return new Promise(() => {}); } // the session ended: go and sign in again
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(describe(data.detail) || `Something went wrong (${res.status}).`);
  return data;
}

async function signOut() {
  await fetch('/api/auth/logout', { method: 'POST' });
  location.href = '/login.html';
}

export const gradeLabel = (grade) => (grade === 0 ? 'Pre-Group' : `Grade ${grade}`);
export const pct = (value) => (value == null ? '–' : `${Math.round(value * 100)}%`);
export const money = (value) => `$${value < 0.1 && value > 0 ? value.toFixed(4) : value.toFixed(2)}`;
export const minutes = (value) => `${value < 10 ? value.toFixed(1) : Math.round(value)} min`;
export const shortDate = (iso) => new Date(`${iso.slice(0, 10)}T00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
export const avatar = (name) => el('span', { class: 'av', style: `--c:${TINTS[[...name].reduce((sum, c) => sum + c.charCodeAt(0), 0) % TINTS.length]}` }, name[0]);

/** A bar showing accuracy, coloured by how the student is doing. */
export function accuracy(value) {
  if (value == null) return el('span', { class: 'note' }, 'No assessments this week');
  const tone = value < 0.5 ? 'coral' : value < 0.7 ? 'sun' : '';
  return el('div', { class: 'acc' }, el('div', { class: `meter ${tone}`, style: 'flex:1' }, el('i', { style: `width:${Math.round(value * 100)}%` })), el('b', {}, pct(value)));
}

// ---- page frame ----
export function shell(active) {
  document.getElementById('side').append(
    el('div', { class: 'brand' }, el('span', { class: 'mark' }, 'Aa'), el('span', {}, 'Open Minds Tutor', el('small', {}, 'Admin'))),
    ...NAV.map(([name, label, href]) => el('a', { href, class: name === active ? 'on' : '' }, icon(name), label)),
    el('div', { class: 'sep' }),
    el('a', { href: '/' }, icon('board'), 'Classroom board'),
    el('button', { class: 'signout', onclick: signOut }, icon('out'), 'Sign out'));
  return document.getElementById('main');
}

export function toast(message) {
  const node = document.body.appendChild(el('div', { class: 'toast', role: 'status' }, message));
  setTimeout(() => node.remove(), 2600);
}

/** fields: [{ name, label, type, options: [[value, label]], value, number, required, ... }]; onSubmit gets {name: value}. */
export function form(fields, submitLabel, onSubmit, layout = '') {
  const error = el('p', { class: 'err', role: 'alert' });
  const inputs = fields.map(({ name, label, options, number, value, ...attrs }) => {
    const input = options
      ? el('select', { name }, options.map(([v, text]) => el('option', { value: v, selected: String(v) === String(value) }, text)))
      : el('input', { name, value, ...attrs });
    input.parse = () => (number ? Number(input.value) : input.value.trim());
    return input;
  });
  const node = el('form', {
    class: `form ${layout}`,
    async onsubmit(event) {
      event.preventDefault();
      error.textContent = '';
      try {
        await onSubmit(Object.fromEntries(fields.map((f, i) => [f.name, inputs[i].parse()])));
        node.reset();
      } catch (err) {
        error.textContent = err.message;
      }
    },
  }, fields.map((f, i) => el('label', {}, f.label, inputs[i])), error, el('button', { class: 'btn primary', type: 'submit' }, submitLabel));
  return node;
}

// ---- charts ----
/** data: [{ label, value | null }]. kind 'line' joins the points (a gap where a week has no value); 'bars' draws one bar each. */
export function chart(data, { kind = 'line', max = 1, format = String } = {}) {
  const W = 560, H = 200, left = 46, top = 12, bottom = 28, plotW = W - left - 8, plotH = H - top - bottom;
  const y = (value) => top + plotH * (1 - value / max);
  const slot = plotW / data.length;
  const x = (i) => left + (kind === 'bars' ? slot * (i + 0.5) : data.length === 1 ? plotW / 2 : (plotW * i) / (data.length - 1));
  const node = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img' });
  for (const t of [0, 0.5, 1]) {
    node.append(svg('line', { x1: left, x2: W - 8, y1: y(max * t), y2: y(max * t), stroke: '#DDE3EF', 'stroke-width': 1.5 }),
      svg('text', { x: left - 8, y: y(max * t) + 4, 'text-anchor': 'end' }, format(max * t)));
  }
  data.forEach((d, i) => node.append(svg('text', { x: x(i), y: H - 8, 'text-anchor': 'middle' }, d.label)));
  if (kind === 'bars') {
    data.forEach((d, i) => d.value && node.append(svg('rect', { x: x(i) - slot * 0.3, y: y(d.value), width: slot * 0.6, height: top + plotH - y(d.value), rx: 6, fill: '#FF8A1F' })));
  } else {
    const path = data.map((d, i) => (d.value == null ? '' : `${i && data[i - 1].value != null ? 'L' : 'M'}${x(i)} ${y(d.value)}`)).join(' ');
    node.append(svg('path', { d: path, fill: 'none', stroke: '#FF8A1F', 'stroke-width': 4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    data.forEach((d, i) => d.value != null && node.append(svg('circle', { cx: x(i), cy: y(d.value), r: 5, fill: i === data.length - 1 ? '#101B3A' : '#fff', stroke: '#FF8A1F', 'stroke-width': 3 })));
  }
  return node;
}
