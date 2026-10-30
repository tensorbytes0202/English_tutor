// English smart board: runs a lesson, speaks through Piper, listens through Whisper, reacts through the tutor model.
const $ = (sel) => document.querySelector(sel);
const ui = Object.fromEntries([
  'stage', 'board', 'className', 'clock', 'lessonTitle', 'lessonExplain', 'visual', 'avatar', 'mouth', 'qNum', 'qText',
  'qWrong', 'options', 'check', 'studentBubble', 'teacherBubble', 'prompt', 'promptForm', 'typed', 'btnType', 'timer',
  'timerRing', 'timerText', 'mic', 'next', 'chat', 'chatList', 'start', 'startNote', 'lessonList', 'voicePick',
  'btnLessons', 'btnRepeat', 'btnChat', 'btnChatClose', 'btnSound', 'btnFull', 'latency',
].map((id) => [id, document.getElementById(id)]));

const LETTERS = 'ABCD';
const RING = 213.6; // circumference of the timer circle (r = 34)
const PROMPTS = {
  choice: 'Now think for a moment... discuss with your partner and share your answer through your microphone.',
  fix: 'Say the corrected sentence into the microphone.',
  speak: 'Answer in one full sentence through your microphone.',
};
const DEBUG = new URLSearchParams(location.search).has('debug'); // open the board with ?debug to see latency
// The mic stops by itself once the student has spoken and then stayed quiet for SILENCE_MS.
// earlyMs: after this much quiet, Whisper starts on what was said so far, while we keep waiting for silenceMs
// to be sure the student is done. If they speak again that early result is thrown away, so nobody is cut off.
const VAD = { minLevel: 0.02, noiseFactor: 2.5, earlyMs: 350, silenceMs: 900, giveUpMs: 8000, maxMs: 20000 };
const PRACTICE = {
  id: 'practice', practice: true, title: 'Free practice',
  explain: 'Say or type any English sentence. The tutor corrects it and explains each mistake.',
  visual: [],
  intro: "Let's practise! Say any sentence in English, and I will check it for you.",
  steps: [{ type: 'speak', question: 'Say any sentence about your day.' }],
  outro: '',
};
const SPOKEN_LETTERS = { a: 0, ay: 0, b: 1, be: 1, bee: 1, c: 2, see: 2, sea: 2, d: 3, dee: 3 };
const FILLER = new Set(['option', 'answer', 'is', 'it', "it's", 'the', 'i', 'think', 'choose', 'letter', 'my', 'number']);

const state = {
  data: null, lesson: null, step: -1, answered: true, voice: 'US female', sound: true,
  score: { right: 0, total: 0 }, lastSpoken: { text: '', brief: false }, timer: null, lessonToken: 0, stepToken: 0,
};
const rec = { recorder: null, stream: null, source: null, meter: 0, limit: 0, heard: false, spec: null, wantSpec: false, speechEnd: 0 };
// Speech arrives one sentence at a time; each is decoded on arrival and played in order through this chain.
const player = { token: 0, chain: Promise.resolve(), source: null, controller: null };
// Latency of one answer, measured from the moment the student finished (stopped talking, tapped or pressed Enter).
const timing = { start: 0, stt: 0, first: 0, done: 0, fromMic: false };
let audioCtx = null;
let mouthOpen = 0;

const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isAbort = (err) => err?.name === 'AbortError';

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function problem(err) {
  const msg = String(err?.message || err);
  return msg.includes('Failed to fetch') ? 'The board server stopped. Start it again, then refresh this page.' : msg;
}

/* ---------- Board size, clock, blinking ---------- */

function fit() {
  if (innerWidth < 900) return; // the stacked phone layout does not scale
  const pad = document.fullscreenElement ? 40 : 110;
  const scale = Math.min((innerWidth - pad) / 1600, (innerHeight - pad) / 900);
  document.documentElement.style.setProperty('--scale', scale.toFixed(4));
}

function tickClock() {
  ui.clock.textContent = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function blinkLoop() {
  setTimeout(() => {
    ui.avatar.classList.add('blink');
    setTimeout(() => ui.avatar.classList.remove('blink'), 140);
    blinkLoop();
  }, 2500 + Math.random() * 3500);
}

/* ---------- Teacher: state, mouth, voice, bubbles, chat ---------- */

const setTeacher = (mode) => { ui.board.dataset.teacher = mode; };

function setMouth(open) {
  ui.mouth.setAttribute('d', `M180 256Q200 ${259 - 4 * open} 220 256Q200 ${266 + 24 * open} 180 256Z`);
}

/* ---------- Speech: replies stream in as events, and each finished sentence is played as soon as it arrives ---------- */

function stopSpeech() {
  player.token++;
  player.chain = Promise.resolve();
  player.controller?.abort();
  player.controller = null;
  if (player.source) {
    try { player.source.stop(); } catch { /* already finished */ }
    player.source = null;
  }
}

function playBuffer(buffer) {
  return new Promise((resolve) => {
    const source = audioCtx.createBufferSource();
    const analyser = audioCtx.createAnalyser();
    const samples = new Uint8Array(512);
    let frame = 0;
    analyser.fftSize = 512;
    source.buffer = buffer;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    const animate = () => { // the mouth opens with the loudness of the voice
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += ((v - 128) / 128) ** 2;
      const target = Math.min(1, Math.sqrt(sum / samples.length) * 7);
      mouthOpen += (target - mouthOpen) * 0.45;
      setMouth(mouthOpen);
      frame = requestAnimationFrame(animate);
    };
    source.onended = () => {
      cancelAnimationFrame(frame);
      mouthOpen = 0;
      setMouth(0);
      if (player.source === source) player.source = null;
      if (ui.board.dataset.teacher === 'speaking') setTeacher('idle');
      resolve();
    };
    player.source = source;
    setTeacher('speaking');
    markTiming('first');
    source.start();
    animate();
  });
}

function queueAudio(base64) {
  const token = player.token;
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const decoded = audioCtx.decodeAudioData(bytes.buffer).catch(() => null); // starts decoding right away
  player.chain = player.chain.then(async () => {
    const buffer = await decoded;
    if (buffer && token === player.token) await playBuffer(buffer);
  });
}

// Read an NDJSON reply: written text, the teacher's opening line, and audio for each finished sentence.
async function readEvents(res, { onText, onSay } = {}) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let text = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    let end;
    while ((end = pending.indexOf('\n')) >= 0) {
      const line = pending.slice(0, end);
      pending = pending.slice(end + 1);
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === 'text') {
        text += event.text;
        onText?.(text);
      } else if (event.type === 'say') {
        onSay?.(event.text, event.tone);
      } else if (event.type === 'audio') {
        queueAudio(event.wav);
      }
    }
  }
  markTiming('done');
  return text.trim();
}

// Ask the server for a spoken reply and wait until it has been fully said.
async function talk(url, body, handlers = {}) {
  stopSpeech();
  const token = player.token;
  player.controller = new AbortController();
  const res = await fetch(url, { ...post({ ...body, voice: state.sound ? state.voice : null }), signal: player.controller.signal });
  if (!res.ok) throw await errorFrom(res);
  handlers.onResponse?.(res);
  const text = await readEvents(res, handlers);
  if (token === player.token) await player.chain;
  return text;
}

async function say(text, brief = false) {
  state.lastSpoken = { text, brief };
  if (!state.sound || !text) return;
  try {
    await talk('/api/say', { text, brief });
  } catch (err) {
    if (!isAbort(err)) console.warn('The teacher could not speak:', err);
  }
}

/* ---------- Latency (shown on the board with ?debug, always logged to the console) ---------- */

function startTiming(fromMic = false) {
  Object.assign(timing, { start: performance.now(), stt: 0, first: 0, done: 0, fromMic });
  if (DEBUG) ui.latency.hidden = true;
}

function markTiming(what) {
  if (!timing.start || timing[what]) return;
  timing[what] = performance.now();
  const s = (t) => (t ? `${((t - timing.start) / 1000).toFixed(1)} s` : '…');
  const line = `${timing.fromMic ? `speech → text ${s(timing.stt)} · ` : ''}first sound ${s(timing.first)} · reply written ${s(timing.done)}`;
  if (timing.first && timing.done) console.info(`[latency] ${line}`);
  if (DEBUG) {
    ui.latency.textContent = line;
    ui.latency.hidden = false;
  }
}

function teacherSays(text, tone = '') {
  ui.teacherBubble.hidden = !text;
  ui.teacherBubble.textContent = text;
  ui.teacherBubble.className = `bubble bubble-teacher ${tone}`.trim();
}

function studentSays(text) {
  ui.studentBubble.hidden = !text;
  ui.studentBubble.textContent = text;
}

function addChat(who, text) {
  const item = el('li', who === 'teacher' ? 'from-teacher' : 'from-student');
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', who === 'teacher' ? '#miniTeacher' : '#miniStudent');
  icon.setAttribute('aria-hidden', 'true');
  icon.append(use);
  const bubble = el('p');
  bubble.append(el('span', 'who', who === 'teacher' ? state.data.teacher : 'Student'), text);
  item.append(icon, bubble);
  ui.chatList.append(item);
  ui.chatList.scrollTop = ui.chatList.scrollHeight;
}

const setPrompt = (text) => { ui.prompt.textContent = text; };

function enableAnswering(on) {
  ui.mic.disabled = !on;
  ui.typed.disabled = !on;
}

async function errorFrom(res) {
  try { return new Error((await res.json()).detail); } catch { return new Error(`The server answered ${res.status}.`); }
}

/* ---------- Lesson picker ---------- */

function renderPicker() {
  const card = (lesson, action, extra = '') => {
    const button = el('button', `lesson-pick ${extra}`.trim());
    button.append(el('strong', '', lesson.title), el('span', '', lesson.explain.split(/(?<=\.)\s/)[0]), el('em', '', action));
    button.addEventListener('click', () => startLesson(lesson));
    return button;
  };
  ui.lessonList.replaceChildren(
    ...state.data.lessons.map((lesson) => card(lesson, 'Start lesson')),
    card(PRACTICE, 'Start practising', 'practice'),
  );
}

function openPicker() {
  stopSpeech();
  stopTimer();
  if (rec.recorder?.state === 'recording') rec.recorder.stop();
  state.lessonToken++;
  state.answered = true;
  setTeacher('idle');
  ui.start.hidden = false;
  ui.lessonList.querySelector('button')?.focus();
}

function showStartError(message) {
  ui.startNote.after(el('p', 'start-error', message));
}

/* ---------- Running a lesson ---------- */

function renderLesson(lesson) {
  ui.lessonTitle.textContent = lesson.title;
  ui.lessonExplain.textContent = lesson.explain;
  ui.visual.replaceChildren(...lesson.visual.map((part) => {
    const chip = el('span', part.mark ? 'chip chip-mark' : 'chip');
    chip.append(el('b', '', part.text), el('small', '', part.label || ''));
    return chip;
  }));
}

function clearQuestion() {
  ui.qNum.textContent = '';
  ui.qText.textContent = '';
  ui.qWrong.hidden = true;
  ui.options.replaceChildren();
  ui.check.hidden = true;
  ui.check.replaceChildren();
}

async function startLesson(lesson) {
  audioCtx ??= new AudioContext();
  if (audioCtx.state === 'suspended') await audioCtx.resume();
  const token = ++state.lessonToken;
  Object.assign(state, { lesson, step: -1, answered: true, score: { right: 0, total: 0 } });
  ui.start.hidden = true;
  ui.chatList.replaceChildren();
  ui.next.hidden = true;
  renderLesson(lesson);
  clearQuestion();
  stopTimer();
  studentSays('');
  enableAnswering(false);
  setPrompt('Listen to the teacher.');
  teacherSays(lesson.intro);
  addChat('teacher', lesson.intro);
  await say(lesson.intro);
  if (!state.sound) await sleep(Math.min(7000, 1500 + lesson.intro.length * 40)); // time to read it
  if (token === state.lessonToken) await showStep(0);
}

function renderStep(step, index) {
  clearQuestion();
  ui.qNum.textContent = state.lesson.practice ? 'Your turn' : `Question ${index + 1} of ${state.lesson.steps.length}`;
  ui.qText.textContent = step.question;
  if (step.type === 'fix') {
    ui.qWrong.textContent = step.wrong;
    ui.qWrong.hidden = false;
  }
  if (step.type === 'choice') {
    ui.options.replaceChildren(...step.options.map((text, k) => {
      const button = el('button', 'option');
      button.dataset.k = k;
      button.append(el('span', 'letter', `${LETTERS[k]})`), el('span', 'text', text), el('span', 'mark'));
      button.addEventListener('click', () => answer({ choice: k }));
      const item = el('li');
      item.append(button);
      return item;
    }));
  }
}

async function showStep(index) {
  const step = state.lesson.steps[index];
  const token = ++state.stepToken;
  Object.assign(state, { step: index, answered: false });
  stopTimer();
  studentSays('');
  teacherSays('');
  ui.next.hidden = true;
  renderStep(step, index);
  setPrompt(PROMPTS[step.type]);
  enableAnswering(true);
  const letters = LETTERS.slice(0, step.options?.length || 0).split('');
  const spoken = step.type === 'choice' ? `${step.question} Is it ${letters.slice(0, -1).join(', ')} or ${letters.at(-1)}?`
    : step.type === 'fix' ? `${step.question} ${step.wrong}` : step.question;
  addChat('teacher', step.type === 'fix' ? `${step.question} “${step.wrong}”` : spoken);
  await say(spoken);
  if (token === state.stepToken && !state.answered && step.type !== 'speak') {
    startTimer(step.seconds || (step.type === 'choice' ? 30 : 45));
  }
}

function matchOption(said, options) {
  const words = said.toLowerCase().replace(/[^a-z0-9' ]/g, ' ').split(/\s+/).filter(Boolean);
  const core = words.filter((w) => !FILLER.has(w));
  if (core.length === 1 && core[0] in SPOKEN_LETTERS && SPOKEN_LETTERS[core[0]] < options.length) {
    return SPOKEN_LETTERS[core[0]];
  }
  let best = null;
  let bestScore = 0;
  options.forEach((option, k) => {
    const optionWords = option.toLowerCase().replace(/[^a-z0-9' ]/g, ' ').split(/\s+/).filter(Boolean);
    const score = optionWords.filter((w) => words.includes(w)).length / optionWords.length;
    if (score > bestScore) [best, bestScore] = [k, score];
  });
  return bestScore >= 0.75 ? best : null;
}

async function answer({ choice = null, said = '' }) {
  const step = state.lesson?.steps[state.step];
  if (!step || state.answered) return;
  if (timing.fromMic) timing.fromMic = false; // timing started when the student stopped talking
  else startTiming();
  if (step.type === 'choice' && choice === null) {
    choice = matchOption(said, step.options);
    if (choice === null) {
      studentSays(said);
      const ask = `I heard “${said}”. Please say A, B, C or D, or tap an option.`;
      teacherSays(ask);
      say(ask);
      return;
    }
  }
  state.answered = true;
  stopTimer();
  stopSpeech();
  enableAnswering(false);
  const shown = step.type === 'choice' && !said ? `${LETTERS[choice]}) ${step.options[choice]}` : said;
  studentSays(shown);
  addChat('student', shown);
  if (step.type === 'choice') ui.options.querySelector(`[data-k="${choice}"]`).classList.add('chosen');
  teacherSays('');
  setTeacher('thinking');
  setPrompt('Checking your answer…');
  try {
    if (step.type === 'speak') await checkSentence(said);
    else await gradeAnswer(step, choice, said);
  } catch (err) {
    if (isAbort(err)) return; // the class moved on (next question, another lesson) while the teacher was replying
    teacherSays(problem(err), 'miss');
  } finally {
    if (ui.board.dataset.teacher === 'thinking') setTeacher('idle');
  }
  finishStep();
}

function revealOptions(step, chosen) {
  ui.options.querySelectorAll('.option').forEach((button) => {
    const k = Number(button.dataset.k);
    button.disabled = true;
    if (k === step.answer) {
      button.classList.add('right');
      button.querySelector('.mark').textContent = '✓';
    } else if (k === chosen) {
      button.classList.add('wrong');
      button.querySelector('.mark').textContent = '✗';
    }
  });
}

async function gradeAnswer(step, choice, said) {
  let correct = false;
  const text = await talk('/api/feedback', { lesson: state.lesson.id, step: state.step, choice, said }, {
    onResponse: (res) => { // right or wrong is known before the teacher says a word
      correct = res.headers.get('X-Correct') === '1';
      state.score.total++;
      if (correct) state.score.right++;
      if (step.type === 'choice') revealOptions(step, choice);
    },
    onText: (t) => {
      if (ui.board.dataset.teacher === 'thinking') setTeacher('idle');
      teacherSays(t, correct ? 'good' : 'miss');
    },
  });
  state.lastSpoken = { text, brief: false };
  addChat('teacher', text);
}

// Everything the corrector wrote between "Corrected:" and the list of mistakes (one or more sentences).
const correctedPart = (text) => text.match(/Corrected:\s*([\s\S]*?)\s*(?:\n\s*(?:Mistakes|Tip):|$)/)?.[1].trim();

function renderCheck(text) { // the student's own words are already in their bubble
  const parts = [];
  if (/^\s*no mistakes/i.test(text)) {
    parts.push(el('p', 'perfect', 'No mistakes. Well done!'));
  } else {
    const fixed = correctedPart(text);
    const changes = [...text.matchAll(/^-\s*"(.+?)"\s*(?:→|->)\s*"(.+?)":?\s*(.*)$/gm)];
    const tip = text.match(/^Tip:\s*(.+)$/m);
    if (fixed) parts.push(el('p', 'fixed', fixed));
    if (changes.length) {
      const list = el('ul');
      for (const [, wrong, right, why] of changes) {
        const item = el('li');
        item.append(el('del', '', wrong), ' → ', el('ins', '', right), why ? `: ${why}` : '');
        list.append(item);
      }
      parts.push(list);
    }
    if (tip) parts.push(el('p', 'tip', `Tip: ${tip[1].trim()}`));
    if (!fixed && !changes.length && text.trim().length > 12) parts.push(el('p', '', text.trim()));
  }
  ui.check.replaceChildren(...parts);
  ui.check.hidden = false;
}

async function checkSentence(said) {
  let line = '';
  const reply = await talk('/api/check', { text: said }, {
    onSay: (text, tone) => { // the teacher reacts as soon as the corrector's first words arrive
      line = text;
      setTeacher('idle');
      teacherSays(text, tone);
    },
    onText: renderCheck,
  });
  const fixed = correctedPart(reply);
  state.lastSpoken = fixed ? { text: `${line}\n${reply}`, brief: true } : { text: line, brief: false };
  addChat('teacher', fixed ? `${line} ${fixed.replace(/\s*\n\s*/g, ' ')}` : line || reply);
}

function finishStep() {
  if (state.lesson.practice) { // practice never ends: the next sentence can come straight away
    state.answered = false;
    enableAnswering(true);
    setPrompt('Say another sentence whenever you are ready.');
    return;
  }
  const last = state.step === state.lesson.steps.length - 1;
  ui.next.textContent = last ? 'Finish lesson' : 'Next question';
  ui.next.hidden = false;
  setPrompt(last ? 'That was the last question.' : 'Press Next question when the class is ready.');
}

async function finishLesson() {
  stopTimer();
  Object.assign(state, { step: state.lesson.steps.length, answered: true });
  enableAnswering(false);
  const { right, total } = state.score;
  clearQuestion();
  ui.qNum.textContent = 'Lesson complete';
  ui.qText.textContent = `${right} of ${total} answers right`;
  studentSays('');
  teacherSays(state.lesson.outro, 'good');
  addChat('teacher', state.lesson.outro);
  setPrompt('Choose another lesson, or practise freely.');
  ui.next.textContent = 'Choose another lesson';
  ui.next.hidden = false;
  await say(state.lesson.outro);
}

function onNext() {
  ui.next.hidden = true;
  if (state.step >= state.lesson.steps.length) openPicker();
  else if (state.step + 1 < state.lesson.steps.length) showStep(state.step + 1);
  else finishLesson();
}

/* ---------- Timer ---------- */

function startTimer(seconds) {
  stopTimer();
  const end = Date.now() + seconds * 1000;
  ui.timer.hidden = false;
  const tick = () => {
    const left = Math.max(0, end - Date.now());
    const s = Math.ceil(left / 1000);
    ui.timerText.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    ui.timerRing.style.strokeDashoffset = RING * (1 - left / (seconds * 1000));
    ui.timer.classList.toggle('low', s <= 5);
    if (left === 0) {
      stopTimer(false);
      timeUp();
    }
  };
  tick();
  state.timer = setInterval(tick, 250);
}

function stopTimer(hide = true) {
  clearInterval(state.timer);
  state.timer = null;
  if (hide) ui.timer.hidden = true;
}

async function timeUp() {
  const step = state.lesson.steps[state.step];
  if (state.answered) return;
  state.answered = true;
  enableAnswering(false);
  state.score.total++;
  let text;
  if (step.type === 'choice') {
    revealOptions(step, null);
    text = `Time's up! The answer is ${LETTERS[step.answer]}: ${step.options[step.answer]} ${step.why}`;
  } else {
    text = `Time's up! The correct sentence is: ${step.answers[0]} ${step.why}`;
  }
  teacherSays(text, 'miss');
  addChat('teacher', text);
  finishStep();
  await say(text);
}

/* ---------- Microphone ---------- */

function startMeter(stream) {
  const analyser = audioCtx.createAnalyser();
  const samples = new Uint8Array(512);
  analyser.fftSize = 512;
  rec.source = audioCtx.createMediaStreamSource(stream);
  rec.source.connect(analyser);
  const began = performance.now();
  let noise = 0;
  let noiseFrames = 0;
  let quietSince = 0;
  rec.heard = false;
  const loop = () => {
    analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (const v of samples) sum += ((v - 128) / 128) ** 2;
    const level = Math.sqrt(sum / samples.length);
    const now = performance.now();
    ui.mic.style.setProperty('--level', Math.min(1, level * 5).toFixed(2));
    if (now - began < 300) { // the first 0.3 s measure the room, so a noisy classroom doesn't count as speech
      noise += level;
      noiseFrames++;
    } else {
      const speaking = level > Math.max(VAD.minLevel, (noise / Math.max(noiseFrames, 1)) * VAD.noiseFactor);
      if (speaking) {
        rec.heard = true;
        quietSince = 0;
        rec.speechEnd = 0;
        rec.wantSpec = false;
        if (rec.spec) { // they carried on talking: that early transcript is out of date
          rec.spec.abort.abort();
          rec.spec = null;
        }
      } else if (rec.heard) {
        quietSince ||= now;
        rec.speechEnd ||= quietSince;
        if (now - quietSince > VAD.earlyMs && !rec.spec && !rec.wantSpec) {
          rec.wantSpec = true;
          rec.recorder.requestData(); // ondataavailable then starts Whisper on everything recorded so far
        }
        if (now - quietSince > VAD.silenceMs) return stopRecording(); // finished speaking
      } else if (now - began > VAD.giveUpMs) {
        return stopRecording(); // nobody said anything
      }
    }
    rec.meter = requestAnimationFrame(loop);
  };
  loop();
}

function stopRecording() {
  if (rec.recorder?.state === 'recording') rec.recorder.stop();
}

function stopMeter() {
  cancelAnimationFrame(rec.meter);
  rec.source?.disconnect();
  ui.mic.style.setProperty('--level', 0);
}

async function toggleMic() {
  if (rec.recorder?.state === 'recording') {
    stopRecording();
    return;
  }
  if (state.answered || ui.mic.disabled) return;
  stopSpeech();
  try {
    rec.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch {
    setPrompt("Microphone access is blocked. Allow the microphone in the browser's address bar, then press the mic again.");
    return;
  }
  const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported(t));
  const recorder = new MediaRecorder(rec.stream, type ? { mimeType: type } : undefined);
  const chunks = [];
  rec.spec = null;
  rec.wantSpec = false;
  rec.speechEnd = 0;
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
    if (rec.wantSpec && recorder.state === 'recording') {
      rec.wantSpec = false;
      rec.spec = requestText(new Blob(chunks.slice(), { type: recorder.mimeType }));
    }
  };
  recorder.onstop = () => {
    startTiming(true);
    if (rec.speechEnd) timing.start = rec.speechEnd; // count from when they actually stopped talking
    clearTimeout(rec.limit);
    stopMeter();
    rec.stream.getTracks().forEach((t) => t.stop());
    if (rec.heard) {
      transcribe(new Blob(chunks, { type: recorder.mimeType }));
    } else {
      timing.start = 0;
      ui.mic.dataset.state = 'idle';
      setTeacher('idle');
      setPrompt("I couldn't hear anything. Press the mic and speak a little closer.");
    }
  };
  rec.recorder = recorder;
  recorder.start();
  stopTimer(); // nobody should run out of time mid-sentence
  setTeacher('listening');
  ui.mic.dataset.state = 'recording';
  ui.mic.setAttribute('aria-label', 'Stop recording');
  setPrompt('Listening… I stop by myself when you finish speaking.');
  startMeter(rec.stream);
  rec.limit = setTimeout(stopRecording, VAD.maxMs);
}

function requestText(blob) {
  const abort = new AbortController();
  const promise = (async () => {
    const res = await fetch('/api/transcribe', { method: 'POST', headers: { 'Content-Type': blob.type || 'audio/webm' }, body: blob, signal: abort.signal });
    if (!res.ok) throw await errorFrom(res);
    return (await res.json()).text;
  })();
  promise.catch(() => {}); // a cancelled early attempt is expected; real callers still see the error
  return { promise, abort };
}

async function transcribe(blob) {
  ui.mic.dataset.state = 'working';
  ui.mic.setAttribute('aria-label', 'Answer with the microphone');
  setTeacher('thinking');
  setPrompt('Writing down what you said…');
  const request = rec.spec || requestText(blob); // the early one is already running if they paused long enough
  rec.spec = null;
  try {
    const text = await request.promise;
    markTiming('stt');
    setTeacher('idle');
    if (text) answer({ said: text });
    else setPrompt("I couldn't hear anything. Press the mic and speak a little closer.");
  } catch (err) {
    setTeacher('idle');
    setPrompt(problem(err));
  } finally {
    ui.mic.dataset.state = 'idle';
  }
}

/* ---------- Controls ---------- */

function toggleSound() {
  state.sound = !state.sound;
  ui.btnSound.setAttribute('aria-pressed', state.sound);
  ui.btnSound.title = state.sound ? "Teacher's voice on" : "Teacher's voice off";
  ui.btnSound.setAttribute('aria-label', state.sound ? "Turn the teacher's voice off" : "Turn the teacher's voice on");
  if (!state.sound) stopSpeech();
}

function toggleChat(open = ui.chat.hidden) {
  ui.chat.hidden = !open;
  ui.btnChat.setAttribute('aria-expanded', open);
  if (open) ui.chatList.scrollTop = ui.chatList.scrollHeight;
}

function bindControls() {
  ui.mic.addEventListener('click', toggleMic);
  ui.next.addEventListener('click', onNext);
  ui.btnLessons.addEventListener('click', openPicker);
  ui.btnRepeat.addEventListener('click', () => state.lastSpoken.text && say(state.lastSpoken.text, state.lastSpoken.brief));
  ui.btnChat.addEventListener('click', () => toggleChat());
  ui.btnChatClose.addEventListener('click', () => toggleChat(false));
  ui.btnSound.addEventListener('click', toggleSound);
  ui.btnFull.addEventListener('click', () => (document.fullscreenElement ? document.exitFullscreen() : ui.stage.requestFullscreen()));
  ui.voicePick.addEventListener('change', () => { state.voice = ui.voicePick.value; });
  ui.btnType.addEventListener('click', () => {
    ui.typed.hidden = !ui.typed.hidden;
    ui.btnType.textContent = ui.typed.hidden ? 'Type instead' : 'Hide typing';
    if (!ui.typed.hidden) ui.typed.focus();
  });
  ui.promptForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const said = ui.typed.value.trim();
    if (said) answer({ said });
    ui.typed.value = '';
  });
  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, select, textarea') || !ui.start.hidden || e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    const step = state.lesson?.steps[state.step];
    if (step?.type === 'choice' && !state.answered && 'abcd'.includes(key) && 'abcd'.indexOf(key) < step.options.length) {
      answer({ choice: 'abcd'.indexOf(key) });
    } else if (key === ' ' || key === 'm') {
      e.preventDefault();
      toggleMic();
    } else if (key === 'n' && !ui.next.hidden) {
      onNext();
    } else if (key === 'escape') {
      toggleChat(false);
    }
  });
}

async function boot() {
  fit();
  addEventListener('resize', fit);
  document.addEventListener('fullscreenchange', fit);
  tickClock();
  setInterval(tickClock, 15000);
  blinkLoop();
  bindControls();
  try {
    state.data = await (await fetch('/api/lessons')).json();
  } catch {
    showStartError('The board server is not running. Start it with: python -m uvicorn server:app --port 7860');
    return;
  }
  ui.className.textContent = state.data.class;
  renderPicker();
  const status = await fetch('/api/status').then((r) => r.json()).catch(() => ({ ollama: false }));
  if (!status.ollama) {
    showStartError("The teacher can't reply yet because Ollama isn't running. Open the Ollama app, then refresh this page.");
  } else if (!status.teacher_ready) {
    showStartError('The teacher model is missing. Run: ollama pull hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M');
  }
  if (status.voices) ui.voicePick.replaceChildren(...status.voices.map((v) => el('option', '', v)));
}

boot();
