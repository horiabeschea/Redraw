"use strict";
/* Lesson screen over the golden set. Signals act instantly (optimistic
 * fallback), then the live policy decision overwrites them. Parent
 * settings come from localStorage (written by /setup). */
const SETUP_WORLDS = { dino: "dinosaur_valley", block: "block_world" };
const WORLD_LABELS = { dinosaur_valley: "Dinosaur valley", block_world: "Block world" };
const SIGNAL_LABELS = { stuck: "I don't get it", bored: "Boring!", explore: "Show it",
                        ready: "Got it", back: "Back to the lesson",
                        say_it: "Say it", tap: "Tap" };
const STRATEGY_TITLES = {
  simplify_language: "Simpler words",
  redraw_simpler: "Simpler words, simpler picture",
  simplify_max: "One idea only",
  offer_support: "Asked a grown-up",
  raise_challenge: "Raised the challenge",
  switch_to_tap_game: "Opened the picture",
  advance: "Moved on",
};
/* Per-step state machine (mirrors policy.py TRANSITIONS "to" column).
 * TEACHING states show the Got-it button; EXPLORE shows Back to the lesson. */
const TEACHING = ["PRESENT", "SIMPLER", "SIMPLEST"];
/* States where an answer is requested: the prompt pill shows here only. */
const PROMPT_STATES = ["TAP_CHECK", "SAY_CHECK", "CHALLENGE", "EXPLORE"];
const FSM_NEXT = {
  "PRESENT|stuck": "SIMPLER", "SIMPLER|stuck": "SIMPLEST",
  "SIMPLEST|stuck": "SUPPORT",
  "PRESENT|bored": "CHALLENGE", "CHALLENGE|bored": "TAP_CHECK",
  "SIMPLER|bored": "EXPLORE", "SIMPLEST|bored": "EXPLORE",
  "CHALLENGE|stuck": "SIMPLER", "EXPLORE|stuck": "SIMPLER",
  "EXPLORE|bored": "CHALLENGE",
  "PRESENT|ready": "TAP_CHECK", "SIMPLER|ready": "TAP_CHECK",
  "SIMPLEST|ready": "TAP_CHECK", "CHALLENGE|ready": "TAP_CHECK",
  "EXPLORE|back_to_PRESENT": "PRESENT", "EXPLORE|back_to_SIMPLER": "SIMPLER",
  "EXPLORE|back_to_SIMPLEST": "SIMPLEST",
  "EXPLORE|back_to_CHALLENGE": "CHALLENGE",
  "EXPLORE|back_to_TAP_CHECK": "TAP_CHECK",
  "EXPLORE|back_to_SAY_CHECK": "SAY_CHECK",
};
/* Optimistic strategy = first allowed entry (== server rule fallback). */
const FSM_FIRST = {
  "PRESENT|stuck": "simplify_language", "SIMPLER|stuck": "redraw_simpler",
  "SIMPLEST|stuck": "offer_support",
  "PRESENT|bored": "raise_challenge", "CHALLENGE|bored": "switch_to_tap_game",
  "SIMPLER|bored": "switch_to_tap_game",
  "SIMPLEST|bored": "switch_to_tap_game",
  "CHALLENGE|stuck": "simplify_language", "EXPLORE|stuck": "simplify_language",
  "EXPLORE|bored": "raise_challenge",
};

const settings = loadSettings();
const state = { pack: null, step: 0, world: null, simple: false, simpleImg: false,
                challenge: false, pressed: null, timeline: [], masks: {},
                backend: "meta", sent: null, showAnalogy: false, _rk: "",
                misses: 0, mastered: [],
                fsm: "PRESENT", stuck: 0, bored: 0, sayTries: 0,
                adaptations: 0, cleanSteps: 0, endedLow: false,
                sayMode: false, expReturn: null, prevWorld: null,
                sessionPrimary: null, rotIdx: 0, expTaps: 0,
                support: false, _busy: false, _lastSig: {}, _signaled: false,
                _step: null, _rotKey: "" };

const $ = (id) => document.getElementById(id);

function loadSettings() {
  try { return JSON.parse(localStorage.getItem("redraw.settings")) || {}; }
  catch (err) { return {}; }
}

function availableWorlds() {
  const picked = (settings.worlds || []).map((w) => SETUP_WORLDS[w]).filter(Boolean);
  return picked.length ? picked : ["dinosaur_valley", "block_world"];
}

function syncWorldPills() {
  document.querySelectorAll("#worlds .pill").forEach((b) => {
    b.setAttribute("aria-pressed", b.textContent === WORLD_LABELS[state.world]);
  });
}

/* World fallback order: current world first, then the other selected ones.
 * Guarantees the render/target/analogy trio always resolves together. */
async function ensureWorld(s) {
  const variant = state.simpleImg ? "masks_simpler" : "masks";
  for (const w of worldChain()) {
    try {
      const meta = await (await fetch(
        `/assets/step${s.step}/${w}/meta.json`)).json();
      if (meta && meta[variant]) {
        if (w !== state.world) {
          state.world = w;
          syncWorldPills();
          log("fallback", "World fallback",
            `This step was missing here, so ${WORLD_LABELS[w]} is showing.`,
            "world → fallback", "rules");
        }
        return;
      }
    } catch (err) { /* try the next selected world */ }
  }
}

async function init() {
  state.pack = await (await fetch("/api/pack")).json();
  try {
    const q = new URLSearchParams({ level: settings.level || "medium",
                                    terms: String(settings.terms || 1) });
    const out = await (await fetch(`/api/captions?${q}`)).json();
    state.captions = Object.fromEntries(
      out.captions.map((c) => [c.step, c]));
  } catch (err) { state.captions = {}; }
  const toggles = settings.toggles || {};
  document.body.classList.toggle("calm", !!(toggles.calm || toggles.motion));
  document.body.classList.toggle("large", !!toggles.large);
  $("calm").setAttribute("aria-pressed", document.body.classList.contains("calm"));
  state.simple = settings.level === "short";

  const worlds = $("worlds");
  const list = availableWorlds();
  state.world = list[0];
  list.forEach((w) => {
    const b = document.createElement("button");
    b.className = "pill";
    b.textContent = WORLD_LABELS[w];
    b.setAttribute("aria-pressed", w === state.world);
    b.onclick = () => {
      // A tap at lesson start declares the session primary; later taps
      // only switch the view.
      if (state.step === 0 && !state._signaled) state.sessionPrimary = w;
      state.world = w; resetStep();
      [...worlds.children].forEach((x) => x.setAttribute("aria-pressed", x === b));
      render();
    };
    worlds.appendChild(b);
  });

  document.querySelectorAll("#signals .signal").forEach((b) => {
    b.onclick = () => signal(b.dataset.signal, b);
  });
  $("read").onclick = speak;
  const readOn = (settings.toggles || {}).read ?? true;
  $("read").classList.toggle("hidden", !readOn);
  $("stopread").classList.toggle("hidden", !readOn);
  $("stopread").onclick = () => speechSynthesis.cancel();
  $("sentnext").onclick = () => {
    const parts = captionSentences();
    state.sent = (state.sent ?? 0) + 1;
    if (state.sent >= parts.length) state.sent = null;
    render();
  };
  $("calm").onclick = (e) => {
    const on = document.body.classList.toggle("calm");
    e.currentTarget.setAttribute("aria-pressed", on);
  };
  $("jurytoggle").onclick = () => {
    document.body.classList.toggle("jury"); renderJury(); drawHotspot();
  };
  $("overlay").addEventListener("click", onTap);
  wireGate();
  wireMic();
  renderJury();
  try {
    state.backend = (await (await fetch("/api/backend")).json()).backend;
  } catch (err) { /* offline page, keep default */ }
  render();
}

function step() { return state.pack.steps[state.step]; }
function imgName() { return state.simpleImg ? "simpler.webp" : "image.webp"; }
function captionFull() {
  const s = step();
  const over = (state.captions || {})[s.step] || {};
  return state.simple
    ? (over.simpler_caption || s.simpler_caption)
    : (over.caption || s.caption);
}
function captionSentences() {
  return captionFull().split(/(?<=[.!?])\s+/).map((x) => x.trim()).filter(Boolean);
}
function stepTitle(s) {
  const n = s.step_name.replace(/_/g, " ");
  return n[0].toUpperCase() + n.slice(1);
}
function policyModel() {
  return state.backend === "baseten" ? "Muse Spark open (private)" : "Muse Spark 1.3";
}

/* Primary world: parent's first pick, unless the child tapped a world at
 * lesson start (explicit session override, never inferred). */
function primaryWorld() { return state.sessionPrimary || availableWorlds()[0]; }
function worldChain() {
  const rest = availableWorlds().filter((w) => w !== state.world);
  return [state.world, ...rest];
}

function resetStep() {
  state.simple = settings.level === "short";
  state.simpleImg = false; state.challenge = false; state.pressed = null;
  state.misses = 0; state.sent = null; state.showAnalogy = false;
  state.stuck = 0; state.bored = 0; state.sayTries = 0; state.adaptations = 0;
  state.sayMode = false; state.expReturn = null; state.support = false;
  // Carry-over: a step that ended low restarts simplified; otherwise standard.
  state.fsm = state.endedLow ? "SIMPLER" : "PRESENT";
  state.simple = state.simple || state.fsm === "SIMPLER";
  if (state.fsm === "SIMPLER") { state.sent = 0; state.showAnalogy = true; }
}

function advanceStep() {
  const low = state.fsm === "SIMPLEST" || state.fsm === "SUPPORT";
  if (state.stuck === 0) state.cleanSteps += 1; else state.cleanSteps = 0;
  state.endedLow = low;
  if (state.prevWorld) { state.world = state.prevWorld; state.prevWorld = null; }
  state.step = Math.min(state.pack.steps.length - 1, state.step + 1);
  resetStep();
}

function speak() {
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance($("caption").textContent));
}

function renderJury() {
  const on = document.body.classList.contains("jury");
  $("viewtag").textContent = on ? "JURY VIEW" : "CHILD VIEW";
  $("viewnote").textContent = on
    ? "Reviewer overlay. The child never sees the dark panel, dashed outlines or model names."
    : "Exactly what the child sees: a picture, a short caption and three big buttons.";
  $("jurytoggle").textContent = on ? "Show what the child sees" : "Show jury overlay";
}

async function render() {
  const s = step();
  const rk = `${s.step}|${state.world}`;
  if (rk !== state._rk) {
    await ensureWorld(s);
    state._rk = `${s.step}|${state.world}`;
    // New masks: misses restart, but sentence-stepping survives a
    // mid-step world switch (rotation, fallback, primary).
    state.misses = 0;
  }
  if (s.step !== state._step) {
    state._step = s.step;
    state.sent = null;
    state.showAnalogy = false;
  }
  const img = $("scene");
  img.dataset.fb = "";
  img.onerror = () => {
    if (img.dataset.fb) { img.onerror = null; return; }
    img.dataset.fb = "1";
    const next = availableWorlds().find((w) => w !== state.world);
    if (!next) { img.onerror = null; return; }
    const missing = `${imgName()} for step ${s.step} in ${WORLD_LABELS[state.world]}`;
    state.world = next;
    syncWorldPills();
    log("fallback", "World fallback",
      `No ${missing}; showing ${WORLD_LABELS[next]} instead.`,
      "world → fallback", "rules");
    img.src = `/assets/step${s.step}/${next}/${imgName()}`;
  };
  img.src = `/assets/step${s.step}/${state.world}/${imgName()}`;
  img.alt = `${WORLD_LABELS[state.world]}: ${s.analogies[state.world] || s.caption}`;
  await img.decode().catch(() => {});
  const parts = captionSentences();
  if (state.sent != null && state.sent >= parts.length) state.sent = null;
  $("caption").textContent = state.sent != null ? parts[state.sent] : captionFull();
  // Reserve the button's space so the card never changes size.
  $("sentnext").style.visibility = state.sent == null ? "hidden" : "visible";
  const analogy = worldChain().map((w) => s.analogies[w]).find(Boolean) || "";
  $("analogy-text").textContent = analogy;
  $("analogy").classList.toggle("hidden", !(state.showAnalogy && analogy));
  $("prompt").textContent = (state.challenge || state.sayMode)
    ? s.say_it.prompt : s.tap_question.prompt;
  $("prompt-pill").classList.toggle("hidden",
    !PROMPT_STATES.includes(state.fsm));
  // Got-it and Back never leave the bar; they disable when inactive.
  $("gotit").disabled = !(TEACHING.includes(state.fsm) && state.sent == null);
  $("back").disabled = state.fsm !== "EXPLORE";
  if (state.fsm !== "EXPLORE") $("back").classList.remove("nudge");
  // A verdict set before render survives it; otherwise clear the old one.
  // The bar resets every render and only fills for a staged advance.
  $("verdict-bar").classList.add("hidden");
  const vfill = $("verdict-fill");
  vfill.style.transition = "none";
  vfill.style.width = "0";
  if (state._verdict) {
    showVerdict(state._verdict.text, state._verdict.ok);
    state._verdict = null;
    if (state._verdictMs) {
      const ms = state._verdictMs; state._verdictMs = null;
      const vbar = $("verdict-bar");
      vbar.classList.remove("hidden");
      void vbar.offsetWidth; // paint the empty bar first, or the fill jumps
      vfill.style.transition = `width ${ms}ms linear`;
      vfill.style.setProperty("--fill-ms", `${ms}ms`);
      vfill.style.width = "100%";
    }
  } else $("verdict-bubble").classList.add("hidden");
  $("way-original").textContent = s.caption;
  $("way-redraw").textContent = s.simpler_caption;
  $("backendnote").textContent = state.backend === "baseten"
    ? "Private mode: open-weight model, no account, no camera."
    : "Standard mode: hosted models, content not used for training. No account, no camera.";
  document.querySelectorAll("#signals .signal").forEach((b) =>
    b.setAttribute("aria-pressed", b.dataset.signal === state.pressed));

  const dots = $("dots");
  dots.innerHTML = "";
  state.pack.steps.forEach((st, i) => {
    const li = document.createElement("li");
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = i < state.step ? "✓" : String(i + 1);
    li.appendChild(mark);
    if (i < state.step) li.classList.add("done");
    if (i === state.step) {
      li.classList.add("current");
      li.setAttribute("aria-current", "step");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = stepTitle(st);
      li.appendChild(name);
    }
    dots.appendChild(li);
  });
  renderTimeline();
  sizeOverlay();
  drawHotspot();
}

function sizeOverlay() {
  const img = $("scene"), cv = $("overlay");
  cv.width = img.clientWidth; cv.height = img.clientHeight;
}

function clearOverlay() {
  const cv = $("overlay");
  cv.getContext("2d").clearRect(0, 0, cv.width, cv.height);
}

async function hotspot() {
  const s = step();
  const variant = state.simpleImg ? "masks_simpler" : "masks";
  const meta = await (await fetch(
    `/assets/step${s.step}/${state.world}/meta.json`)).json();
  const raw = ((meta || {})[variant] || {})[s.tap_question.target_noun];
  if (!raw || !raw.box)
    throw new Error(`no hotspot ${s.tap_question.target_noun} in ` +
      `step${s.step}/${state.world}/${variant}`);
  const entry = { ...raw, mask_png: raw.mask_dilated_png || raw.mask_png };
  return { entry, noun: s.tap_question.target_noun };
}

async function maskPixels(world, stepN, png) {
  const key = `${stepN}/${world}/${png}`;
  if (!state.masks[key]) {
    const img = new Image();
    img.src = `/assets/step${stepN}/${world}/${png}`;
    await img.decode();
    const cv = document.createElement("canvas");
    cv.width = img.naturalWidth; cv.height = img.naturalHeight;
    const ctx = cv.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    state.masks[key] = { data: ctx.getImageData(0, 0, cv.width, cv.height).data,
                         w: cv.width, h: cv.height };
  }
  return state.masks[key];
}

async function inside(entry, s, x, y) {
  // A missing/unreadable mask file falls back to its hand box, never dead.
  if (entry.mask_png && entry.raster) {
    try {
      const m = await maskPixels(state.world, s.step, entry.mask_png);
      const [mh, mw] = entry.raster;
      const sx = (entry.box.right - entry.box.left) / mw;
      const sy = (entry.box.bottom - entry.box.top) / mh;
      if (x < entry.box.left || x >= entry.box.right ||
          y < entry.box.top || y >= entry.box.bottom) return false;
      const col = Math.min(mw - 1, Math.floor((x - entry.box.left) / sx));
      const row = Math.min(mh - 1, Math.floor((y - entry.box.top) / sy));
      return m.data[(row * m.w + col) * 4] > 0;
    } catch (err) { /* fall through to the box test */ }
  }
  const b = entry.box;
  return b.left <= x && x < b.right && b.top <= y && y < b.bottom;
}

function showVerdict(text, ok) {
  $("verdict-text").textContent = text;
  const v = $("verdict-bubble");
  v.classList.toggle("ok", ok);
  v.classList.remove("hidden");
}

/* Praise with a filling bar, then advance: the child sees the win for
 * ~2.5 s before the step moves on. */
function praiseThenAdvance(text, ms = 2500) {
  state._verdict = { text, ok: true };
  state._verdictMs = ms;
  render();
  const token = `${state.step}|${state.world}`;
  setTimeout(() => {
    if (`${state.step}|${state.world}` === token) { advanceStep(); render(); }
  }, ms);
}

function speakText(t) {
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(t));
}

function readOn() {
  return (settings.toggles || {}).read ?? true;
}

function calmOn() {
  return document.body.classList.contains("calm");
}

function chime() {
  if (calmOn()) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const t0 = ctx.currentTime;
    [[659.25, 0], [440, 0.18]].forEach(([freq, dt]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(0.12, t0 + dt + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.3);
      o.connect(g).connect(ctx.destination);
      o.start(t0 + dt); o.stop(t0 + dt + 0.35);
    });
  } catch (err) { /* silent without audio */ }
}

async function glowHotspot(entry) {
  const cv = $("overlay"), ctx = cv.getContext("2d");
  const img = $("scene");
  const m = await maskPixels(state.world, step().step, entry.mask_png);
  const pic = document.createElement("canvas");
  pic.width = m.w; pic.height = m.h;
  const pctx = pic.getContext("2d");
  const data = pctx.createImageData(m.w, m.h);
  for (let i = 0; i < m.w * m.h; i++) {
    data.data[i * 4] = 64; data.data[i * 4 + 1] = 186;
    data.data[i * 4 + 2] = 155; data.data[i * 4 + 3] = m.data[i * 4];
  }
  pctx.putImageData(data, 0, 0);
  const kx = cv.width / img.naturalWidth, ky = cv.height / img.naturalHeight;
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.drawImage(pic, entry.box.left * kx, entry.box.top * ky,
    (entry.box.right - entry.box.left) * kx,
    (entry.box.bottom - entry.box.top) * ky);
}

function pulseHotspot(entry, done) {
  const cv = $("overlay"), ctx = cv.getContext("2d");
  const img = $("scene");
  const kx = cv.width / img.naturalWidth, ky = cv.height / img.naturalHeight;
  const x = entry.box.left * kx, y = entry.box.top * ky;
  const w = (entry.box.right - entry.box.left) * kx;
  const h = (entry.box.bottom - entry.box.top) * ky;
  let n = 0;
  const frame = () => {
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = `rgba(64,186,155,${0.1 + 0.15 * Math.abs(Math.sin(n / 3))})`;
    ctx.fillRect(x, y, w, h);
    if (++n < 12) requestAnimationFrame(frame);
    else { ctx.clearRect(0, 0, cv.width, cv.height); if (done) done(); }
  };
  frame();
}

function prefetchNext() {
  const n = state.step + 1;
  if (n >= state.pack.steps.length) return;
  ["image.webp", "simpler.webp"].forEach((f) => {
    const im = new Image();
    im.src = `/assets/step${state.pack.steps[n].step}/${state.world}/${f}`;
  });
}

function tapPoint(e) {
  const img = $("scene");
  const r = img.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width * img.naturalWidth,
          (e.clientY - r.top) / r.height * img.naturalHeight];
}

/* EXPLORE detour: free tapping, no grading, no counters. Names the part. */
async function exploreTap(e) {
  const s = step();
  const [x, y] = tapPoint(e);
  let meta = null;
  try {
    meta = await (await fetch(
      `/assets/step${s.step}/${state.world}/meta.json`)).json();
  } catch (err) { return showVerdict("Keep looking around.", true); }
  const variant = state.simpleImg ? "masks_simpler" : "masks";
  for (const [noun, raw] of Object.entries((meta || {})[variant] || {})) {
    const entry = { ...raw, mask_png: raw.mask_dilated_png || raw.mask_png };
    if (await inside(entry, s, x, y)) {
      const text = `That's the ${noun}.`;
      showVerdict(text, true);
      if (readOn()) speakText(text);
      // Soft nudge only: after 6 named taps the exit grows, never forces.
      state.expTaps += 1;
      if (state.expTaps === 6) $("back").classList.add("nudge");
      return;
    }
  }
  showVerdict("Keep looking around.", true);
}

async function onTap(e) {
  const s = step();
  // A tap while teaching means the child is ready: enter TAP_CHECK first.
  if (TEACHING.includes(state.fsm) || state.fsm === "CHALLENGE") {
    state.fsm = "TAP_CHECK";
    state.sayMode = false;
    state._signaled = true;
    log("ready", "Started the check", "First tap on the scene opens the check.",
        "ready → TAP_CHECK", "rules");
  }
  if (state.fsm === "EXPLORE") return exploreTap(e);
  if (state.fsm !== "TAP_CHECK") return;
  let entry = null, noun = "";
  try {
    ({ entry, noun } = await hotspot());
  } catch (err) {
    showVerdict("Try tapping again.", false);
    log("tap", "Tap check unavailable",
      String((err && err.message) || err), "tap_error", "rules");
    return;
  }
  if (!entry) return;
  const [x, y] = tapPoint(e);
  const hit = await inside(entry, s, x, y);
  if (hit) {
    state.misses = 0;
    if (!state.mastered.includes(s.step_name)) state.mastered.push(s.step_name);
    const meaning = s.analogies[state.world] || "";
    const text = `Yes! That's the ${noun}.`;
    state._verdict = { text, ok: true };
    if (s.say_it && s.say_it.prompt) {
      state.fsm = "SAY_CHECK";
      state.sayMode = true;
      log("tap", `Tapped the ${noun}: correct`, meaning,
        "tap_correct → SAY_CHECK", "SAM 3.1");
    } else {
      log("tap", `Tapped the ${noun}: correct`, meaning,
        "tap_correct → ADVANCE (no say-it)", "SAM 3.1");
      praiseThenAdvance(text, 2500);
    }
    if (state.fsm === "SAY_CHECK") render();
    if (entry.mask_png) await glowHotspot(entry);
    if (readOn()) speakText(text);
    chime();
    prefetchNext();
    return;
  }
  state.misses += 1;
  if (state.misses >= 3) {
    const token = `${state.step}|${state.world}`;
    drawHotspot(true);
    const text = `There is the ${noun}.`;
    showVerdict(text, true);
    if (readOn()) speakText(text);
    log("tap", `Tap missed three times: revealed the ${noun}`,
      "Three misses, so the answer is shown and the say-it check follows.",
      "tap_miss_limit → SAY_CHECK (reveal)", "SAM 3.1");
    setTimeout(() => {
      if (`${state.step}|${state.world}` === token) {
        state.fsm = "SAY_CHECK";
        state.sayMode = true;
        render();
      }
    }, 1500);
    return;
  }
  if (state.misses >= 2) pulseHotspot(entry);
  showVerdict(`Not quite. Look for the ${noun} and try again.`, false);
  log("tap", `Tapped near the ${noun}`,
    "The tap landed outside the mask. No wrong message, try again.",
    "tap_miss", "SAM 3.1");
}

async function drawHotspot(force) {
  clearOverlay();
  if (!force && !document.body.classList.contains("jury")) return;
  const { entry, noun } = await hotspot();
  const cv = $("overlay"), ctx = cv.getContext("2d");
  const img = $("scene");
  const kx = cv.width / img.naturalWidth, ky = cv.height / img.naturalHeight;
  const x = entry.box.left * kx, y = entry.box.top * ky;
  const w = (entry.box.right - entry.box.left) * kx;
  const h = (entry.box.bottom - entry.box.top) * ky;
  ctx.fillStyle = "rgba(22,119,109,0.2)";
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = "#C9461F"; ctx.lineWidth = 3; ctx.setLineDash([9, 6]);
  ctx.strokeRect(x, y, w, h);
  ctx.setLineDash([]);
  ctx.font = "800 14px Nunito, system-ui, sans-serif";
  const tw = ctx.measureText(noun).width + 24;
  const ly = Math.min(y + h + 4, cv.height - 30);
  ctx.fillStyle = "#C9461F";
  ctx.beginPath(); ctx.roundRect(x + w / 2 - tw / 2, ly, tw, 26, 13); ctx.fill();
  ctx.fillStyle = "#FFFFFF"; ctx.textAlign = "center";
  ctx.fillText(noun, x + w / 2, ly + 18);
}

function learner() {
  return { current_step: state.step + 1, world: state.world, mastered: state.mastered,
           stuck_count: 0, bored_count: 0 };
}

/* Deterministic lesson events: no model call, resolved from FSM_NEXT. */
function fireEvent(ev) {
  const from = state.fsm;
  if (ev === "back") {
    if (from !== "EXPLORE") return;
    // Resolve through the table: back_to_<origin>, counters unchanged.
    const resolved = `back_to_${state.expReturn || "TAP_CHECK"}`;
    state.fsm = FSM_NEXT[`EXPLORE|${resolved}`] || "TAP_CHECK";
    state.expReturn = null;
    state._signaled = true;
    log("back", "Back to the lesson",
        `Left the detour, returned to ${state.fsm}.`,
        `${resolved} → ${state.fsm}`, "rules");
    render();
    return;
  }
  const to = FSM_NEXT[`${from}|${ev}`];
  if (!to) return;
  state.pressed = ev === "ready" ? "ready" : state.pressed;
  state.fsm = to;
  state.sayMode = false;
  state._signaled = true;
  log("ready", "Started the check", "The caption is in, so the tap check opens.",
      `ready → ${to}`, "rules");
  render();
}

function countSignal(kind) {
  if (kind === "stuck") { state.stuck += 1; state.cleanSteps = 0; }
  if (kind === "bored") state.bored += 1;
  state.adaptations += 1;
}

async function signal(kind, anchor) {
  const s = step();
  state._signaled = true;
  if (kind === "ready" || kind === "back") return fireEvent(kind);
  const now = Date.now();
  // Guard: debounce repeat presses; one redraw in flight; cap adaptations.
  if (state._lastSig[kind] && now - state._lastSig[kind] < 2000) return;
  state._lastSig[kind] = now;
  if (state._busy) return;
  if (state.adaptations >= 3) {
    log(kind, "Moved on", "Three adaptations already; the lesson moves on.",
        `${kind} → advance (cap)`, "rules");
    advanceStep(); render();
    return;
  }
  const from = state.fsm;
  state.pressed = kind;
  const first = FSM_FIRST[`${from}|${kind}`]
    || (kind === "explore" ? "switch_to_tap_game" : "simplify_language");
  const to = FSM_NEXT[`${from}|${kind}`] || from;
  // Instant optimistic render; the live decision overwrites the strategy.
  applyStrategy(first, to, from);
  countSignal(kind);
  state._busy = true;
  setSparkWaiting(true, anchor);
  try {
    const res = await fetch("/api/policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signal: kind,
        step: { step: s.step, step_name: s.step_name },
        learner: learner(),
        fsm: { state: from, stuck: state.stuck, bored: state.bored } }),
    });
    if (!res.ok) {
      setSparkWaiting(false, anchor);
      let detail = "";
      try {
        const e = await res.json();
        if (e && e.error) detail = `: ${e.error}`;
      } catch (err) { /* non-JSON error page */ }
      log(kind, `Policy HTTP ${res.status}`,
        `The server answered with an error${detail}. Kept the instant change.`,
        `${kind} → fallback`, "rules");
      state._busy = false;
      return;
    }
    const out = await res.json();
    setSparkWaiting(false, anchor);
    const d = out.decision;
    applyStrategy(d.strategy, out.next_state || to, from);
    log(d.signal, STRATEGY_TITLES[d.strategy] || d.strategy.replace(/_/g, " "),
        `${d.reason} (${out.ms} ms${out.cached ? ", cached" : ""})`,
        `${d.signal} → ${d.strategy}`, policyModel());
  } catch (err) {
    setSparkWaiting(false, anchor);
    log(kind, "Kept the instant change", "Policy unreachable, rule fallback used.",
        `${kind} → fallback`, "rules");
  }
  state._busy = false;
}

function applyStrategy(strategy, to, from) {
  state.fsm = to || state.fsm;
  if (strategy === "simplify_language") {
    state.simple = true;
    state.sent = 0;
    state.showAnalogy = true;
  }
  if (strategy === "redraw_simpler") {
    state.simple = true;
    state.simpleImg = true;
    state.sent = 0;
    state.showAnalogy = true;
  }
  if (strategy === "simplify_max") {
    // SIMPLEST: one idea, one picture, the primary (most familiar) world.
    state.simple = true;
    state.simpleImg = true;
    state.sent = 0;
    state.showAnalogy = false;
    if (state.world !== primaryWorld()) {
      state.prevWorld = state.prevWorld || state.world;
      state.world = primaryWorld();
      syncWorldPills();
    }
  }
  if (strategy === "offer_support") {
    state.support = true;
    state.fsm = "SUPPORT";
    log("stuck", "Asked a grown-up",
        "Three kinds of simpler did not land; flagged for the parent report.",
        "stuck → offer_support", policyModel());
    praiseThenAdvance("Let's ask a grown-up to explore this together.", 4000);
    return;
  }
  if (strategy === "raise_challenge") {
    state.challenge = true;
    state.sayMode = false;
  }
  if (strategy === "switch_to_tap_game") {
    state.challenge = false;
    state.sayMode = false;
    if (state.fsm === "EXPLORE") {
      state.expReturn = from;
      state.expTaps = 0;
      $("back").classList.remove("nudge");
    }
  }
  // World rotation: SIMPLER and CHALLENGE cycle the selected worlds;
  // SIMPLEST always uses the primary world. Once per transition: the
  // optimistic pass and the live answer share one rotation.
  const rotKey = `${state.step}|${from}|${to}`;
  if ((to === "SIMPLER" || to === "CHALLENGE") && availableWorlds().length > 1
      && state._rotKey !== rotKey) {
    state._rotKey = rotKey;
    const list = availableWorlds();
    state.world = list[state.rotIdx % list.length];
    state.rotIdx += 1;
    syncWorldPills();
  }
  if (strategy === "advance") advanceStep();
  render();
}

async function gradeSayIt(answer, anchor) {
  const inCheck = state.fsm === "SAY_CHECK";
  try {
    setSparkWaiting(true, anchor);
    const res = await fetch("/api/sayit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, step: step().step }),
    });
    const r = (await res.json()).result;
    setSparkWaiting(false, anchor);
    // The child sees only short confirmations and kind questions; the
    // explanation (answer-key reasoning) belongs to the jury log below.
    showVerdict(r.verdict === "ok" ? "Yes! Well said." : (r.hint || r.explanation),
      r.verdict === "ok");
    if (r.verdict === "ok") {
      log("say_it", "Said it right", `${r.explanation}`.trim(),
        inCheck ? "say_ok → ADVANCE" : "say_it → ok", policyModel());
      if (inCheck) { praiseThenAdvance("Yes! Well said.", 2500); return; }
      return;
    }
    if (inCheck) {
      state.sayTries += 1;
      if (state.sayTries >= 2) {
        log("say_it", "Moved on",
          `${r.explanation} ${r.hint}`.trim(),
          "say_partial_limit → ADVANCE", policyModel());
        praiseThenAdvance(r.hint || r.explanation, 2500);
        return;
      }
      log("say_it", "Gave a hint", `${r.explanation} ${r.hint}`.trim(),
        "say_partial → SAY_CHECK (one more try)", policyModel());
      return;
    }
    log("say_it", "Gave a hint", `${r.explanation} ${r.hint}`.trim(),
      "say_it → partial", policyModel());
  } catch (err) {
    setSparkWaiting(false, anchor);
    log("say_it", "Answer kept", "Grading unreachable, answer saved.",
        "say_it → saved", "rules");
  }
}

function wireGate() {
  const quiz = [
    { text: "What is 7 × 8?", opts: [54, 56, 58, 63], right: 56 },
    { text: "What is 13 + 29?", opts: [41, 52, 42, 32], right: 42 },
  ];
  const show = (id) => ["gate-quiz", "gate-fail", "gate-ok"].forEach((x) =>
    $(x).classList.toggle("hidden", x !== id));
  const ask = (i) => {
    if (i >= quiz.length) return show("gate-ok");
    show("gate-quiz");
    $("gate-q").textContent = quiz[i].text;
    const box = $("gate-answers");
    box.innerHTML = "";
    quiz[i].opts.forEach((v) => {
      const b = document.createElement("button");
      b.textContent = v;
      b.onclick = () => (v === quiz[i].right ? ask(i + 1) : show("gate-fail"));
      box.appendChild(b);
    });
  };
  $("lock").onclick = () => { $("gate").classList.remove("hidden"); ask(0); };
  $("gate-retry").onclick = () => ask(0);
  $("gate-close").onclick = () => $("gate").classList.add("hidden");
}

const WORKLET = `class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("tap", Tap);`;

async function recordWav() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = new AudioContext({ sampleRate: 16000 });
  await ctx.audioWorklet.addModule(URL.createObjectURL(
    new Blob([WORKLET], { type: "application/javascript" })));
  const src = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "tap");
  const chunks = [];
  node.port.onmessage = (e) => chunks.push(new Float32Array(e.data));
  src.connect(node);
  const an = ctx.createAnalyser(); an.fftSize = 512;
  const anBuf = new Float32Array(an.fftSize);
  src.connect(an);
  const level = () => {
    an.getFloatTimeDomainData(anBuf);
    let sum = 0;
    for (let i = 0; i < anBuf.length; i++) sum += anBuf[i] * anBuf[i];
    return Math.sqrt(sum / anBuf.length);
  };
  return { level, stop: async () => {
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
    const n = chunks.reduce((a, c) => a + c.length, 0);
    const data = new Float32Array(n);
    let o = 0;
    chunks.forEach((c) => { data.set(c, o); o += c.length; });
    const buf = new ArrayBuffer(44 + n * 2);
    const v = new DataView(buf);
    const wstr = (p, s) => { for (let i = 0; i < s.length; i++) v.setUint8(p + i, s.charCodeAt(i)); };
    wstr(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); wstr(8, "WAVE");
    wstr(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, 1, true); v.setUint32(24, 16000, true);
    v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    wstr(36, "data"); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++)
      v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, data[i])) * 32767, true);
    return new Blob([buf], { type: "audio/wav" });
  } };
}

function heard(text, by) {
  $("heard").textContent = text;
  $("heardby").textContent = by || "";
  $("heard-bubble").classList.remove("hidden");
}

/* Spinner on the control that asked: the pressed button or the mic. */
const waitingBtns = new Set();
function setSparkWaiting(on, btn) {
  if (!btn) return;
  if (on) waitingBtns.add(btn); else waitingBtns.delete(btn);
  btn.classList.toggle("waiting", waitingBtns.has(btn));
}

/* Hold "Say it": a signal phrase steers the lesson; anything else is
 * graded as the child's say-it answer. */
function wireMic() {
  const btn = $("mic");
  let rec = null, meterId = 0;
  const start = async (e) => {
    e.preventDefault();
    try {
      rec = await recordWav(); btn.classList.add("active");
      const tick = () => {
        if (!rec) return;
        let lv = 0;
        try { lv = Math.min(1, rec.level() * 4); } catch (err) { /* closed */ }
        $("miclevel").style.width = `${Math.round(lv * 100)}%`;
        meterId = requestAnimationFrame(tick);
      };
      tick();
    }
    catch (err) { heard("No microphone. Use the buttons."); rec = null; }
  };
  const stop = async () => {
    if (!rec) return;
    cancelAnimationFrame(meterId);
    $("miclevel").style.width = "0";
    btn.classList.remove("active");
    const blob = await rec.stop();
    rec = null;
    const secs = Math.max(0, (blob.size - 44) / 2 / 16000);
    if (secs < 0.3) {
      heard(`Too short (${secs.toFixed(1)}s). Hold the button while you talk.`);
      return;
    }
    const fd = new FormData();
    fd.append("audio", blob, "clip.wav");
    try {
      const res = await fetch("/api/voice", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = "";
        try {
          const e = await res.json();
          if (e && e.error) detail = `: ${e.error}`;
        } catch (err) { /* non-JSON error page */ }
        return heard(`Voice problem${detail}. Use the buttons.`);
      }
      const out = await res.json();
      if (!out.text)
        return heard(`Heard nothing (${secs.toFixed(1)}s clip). Try again, holding the button.`);
      // Low-confidence guard: a fragment this short never steers or grades.
      if (out.text.trim().length < 3) {
        heard("Say it again, clearly.");
        return;
      }
      heard(`“${out.text}”`, "Jury note: heard by Muse Voice Transcribe");
      $("heardspin").classList.remove("hidden");
      if (out.signal) await signal(out.signal, btn);
      else await gradeSayIt(out.text, btn);
      $("heardspin").classList.add("hidden");
      // The transcription served its purpose; the reply stands on its own.
      $("heard-bubble").classList.add("hidden");
    } catch (err) {
      heard("Voice failed. Use the buttons.");
    }
  };
  btn.addEventListener("pointerdown", start);
  btn.addEventListener("pointerup", stop);
  btn.addEventListener("pointerleave", stop);
}

function log(signalKind, title, reason, decision, by) {
  state.timeline.unshift({ chip: SIGNAL_LABELS[signalKind] || signalKind,
    step: `Step ${step().step}`, title, reason, decision, by });
  renderTimeline();
}

function renderTimeline() {
  const tl = $("timeline");
  tl.innerHTML = "";
  if (!state.timeline.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No changes yet. Press a button, tap the picture or say something.";
    tl.appendChild(li);
    return;
  }
  state.timeline.forEach((t) => {
    const li = document.createElement("li");
    const add = (cls, text, parent = li) => {
      const el = document.createElement(cls === "chip" || cls === "meta" ? "span" : "div");
      el.className = cls; el.textContent = text; parent.appendChild(el);
    };
    const head = document.createElement("div");
    li.appendChild(head);
    add("chip", t.chip, head);
    add("meta", t.step, head);
    add("title", t.title);
    add("reason", t.reason);
    add("decision", `${t.decision} · ${t.by}`);
    tl.appendChild(li);
  });
}

window.addEventListener("resize", () => { sizeOverlay(); drawHotspot(); });
init();
