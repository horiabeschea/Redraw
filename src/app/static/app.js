"use strict";
/* Lesson screen: golden set only, no live calls. Signals act locally;
 * the policy (Muse Spark) replaces the stub log() in a later step. */
const state = { pack: null, step: 0, world: "dinosaur_valley",
                simple: false, tapMode: false, timeline: [], masks: {} };

const $ = (id) => document.getElementById(id);

async function init() {
  state.pack = await (await fetch("/api/pack")).json();
  const worlds = $("worlds");
  ["dinosaur_valley", "block_world"].forEach((w) => {
    const b = document.createElement("button");
    b.textContent = w === "dinosaur_valley" ? "Dinosaurs" : "Blocks";
    b.dataset.world = w;
    if (w === state.world) b.classList.add("active");
    b.onclick = () => { state.world = w; state.simple = false; state.simpleImg = false;
      [...worlds.children].forEach((x) => x.classList.toggle("active", x === b));
      render(); };
    worlds.appendChild(b);
  });
  document.querySelectorAll("#signals button").forEach((b) => {
    b.onclick = () => signal(b.dataset.signal);
  });
  $("prev").onclick = () => { state.step = Math.max(0, state.step - 1);
    state.simple = false; state.simpleImg = false; render(); };
  $("next").onclick = () => { state.step = Math.min(4, state.step + 1);
    state.simple = false; state.simpleImg = false; render(); };
  $("read").onclick = () => {
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance($("caption").textContent));
  };
  $("calm").onclick = (e) => {
    const on = document.body.classList.toggle("calm");
    e.target.setAttribute("aria-pressed", on);
  };
  $("tapmode").onclick = () => { state.tapMode = !state.tapMode;
    $("tapmode").classList.toggle("active", state.tapMode); };
  $("overlay").addEventListener("click", onTap);
  wireMic();
  wirePrivate();
  $("saysave").onclick = async () => {
    const v = $("sayit").value.trim();
    if (!v) return;
    try {
      const res = await fetch("/api/sayit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer: v, step: step().step }),
      });
      const out = await res.json();
      const r = out.result;
      $("verdict").textContent = r.verdict === "ok"
        ? r.explanation
        : `${r.explanation} ${r.hint}`;
      log("say_it", r.verdict, `${r.explanation} ${r.hint}`.trim());
    } catch (err) {
      log("say_it", "saved", "grading unreachable, answer kept");
    }
    $("sayit").value = "";
  };
  render();
}

function step() { return state.pack.steps[state.step]; }
function imgName() { return state.simpleImg ? "simpler.webp" : "image.webp"; }

async function render() {
  const s = step();
  const img = $("scene");
  img.src = `/assets/step${s.step}/${state.world}/${imgName()}`;
  await img.decode().catch(() => {});
  $("caption").textContent = state.simple ? s.simpler_caption : s.caption;
  $("tapq").textContent = s.tap_question.prompt;
  $("sayitq").textContent = s.say_it.prompt;
  $("verdict").textContent = "";
  const dots = $("dots");
  dots.innerHTML = "";
  state.pack.steps.forEach((_, i) => {
    const li = document.createElement("li");
    if (i <= state.step) li.classList.add("done");
    dots.appendChild(li);
  });
  sizeOverlay();
  if (state.tapMode) drawHotspot();
  else clearOverlay();
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
  return { entry: meta[variant][s.tap_question.target_noun], noun: s.tap_question.target_noun };
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
  if (entry.mask_png) {
    const m = await maskPixels(state.world, s.step, entry.mask_png);
    const [mh, mw] = entry.raster;
    const sx = (entry.box.right - entry.box.left) / mw;
    const sy = (entry.box.bottom - entry.box.top) / mh;
    if (x < entry.box.left || x >= entry.box.right ||
        y < entry.box.top || y >= entry.box.bottom) return false;
    const col = Math.min(mw - 1, Math.floor((x - entry.box.left) / sx));
    const row = Math.min(mh - 1, Math.floor((y - entry.box.top) / sy));
    return m.data[(row * m.w + col) * 4] > 0;
  }
  const b = entry.box;
  return b.left <= x && x < b.right && b.top <= y && y < b.bottom;
}

async function onTap(e) {
  if (!state.tapMode) return;
  const s = step();
  const { entry, noun } = await hotspot();
  const r = $("scene").getBoundingClientRect();
  const img = $("scene");
  const x = (e.clientX - r.left) / r.width * img.naturalWidth;
  const y = (e.clientY - r.top) / r.height * img.naturalHeight;
  const hit = await inside(entry, s, x, y);
  $("verdict").textContent = hit
    ? `Yes! That's the ${noun}.`
    : `Not quite - that's not the ${noun}. Look for the big ${noun} and try again.`;
  drawHotspot();
}

async function drawHotspot() {
  clearOverlay();
  const s = step();
  const { entry } = await hotspot();
  const cv = $("overlay"), ctx = cv.getContext("2d");
  const img = $("scene");
  const kx = cv.width / img.naturalWidth, ky = cv.height / img.naturalHeight;
  ctx.fillStyle = "rgba(46,125,79,0.25)";
  ctx.fillRect(entry.box.left * kx, entry.box.top * ky,
               (entry.box.right - entry.box.left) * kx,
               (entry.box.bottom - entry.box.top) * ky);
}

function learner() {
  return { current_step: state.step + 1, world: state.world, mastered: [],
           stuck_count: 0, bored_count: 0 };
}

async function signal(kind) {
  const s = step();
  // Instant optimistic fallback (policy takes ~6s live); the real
  // decision overwrites it when it lands.
  applyStrategy(kind === "got_it" ? "advance"
    : kind === "bored" ? "switch_to_tap_game" : "simplify_language");
  try {
    const res = await fetch("/api/policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signal: kind,
        step: { step: s.step, step_name: s.step_name, stuck_count: 0 },
        learner: learner() }),
    });
    const out = await res.json();
    applyStrategy(out.decision.strategy);
    log(out.decision.signal, out.decision.strategy,
        `${out.decision.reason} (${out.ms} ms${out.cached ? ", cached" : ""})`);
  } catch (err) {
    log(kind, "fallback", "policy unreachable, kept instant change");
  }
}

function applyStrategy(strategy) {
  if (strategy === "simplify_language") state.simple = true;
  if (strategy === "redraw_simpler") {
    state.simple = true;
    state.simpleImg = true;
  }
  if (strategy === "switch_to_tap_game" || strategy === "raise_challenge") {
    state.tapMode = true;
    $("tapmode").classList.add("active");
  }
  if (strategy === "advance") {
    state.simple = false; state.simpleImg = false;
    state.step = Math.min(4, state.step + 1);
  }
  render();
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
  return { stop: async () => {
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

function wireMic() {
  const btn = $("mic");
  let rec = null;
  const start = async (e) => {
    e.preventDefault();
    try { rec = await recordWav(); btn.classList.add("active"); }
    catch (err) { $("heard").textContent = "No microphone. Use the buttons."; rec = null; }
  };
  const stop = async () => {
    if (!rec) return;
    btn.classList.remove("active");
    const blob = await rec.stop();
    rec = null;
    const fd = new FormData();
    fd.append("audio", blob, "clip.wav");
    try {
      const res = await fetch("/api/voice", { method: "POST", body: fd });
      const out = await res.json();
      $("heard").textContent = out.text ? `Heard: ${out.text}` : "Heard nothing.";
      if (out.signal) signal(out.signal);
    } catch (err) {
      $("heard").textContent = "Voice failed. Use the buttons.";
    }
  };
  btn.addEventListener("pointerdown", start);
  btn.addEventListener("pointerup", stop);
  btn.addEventListener("pointerleave", stop);
}

async function wirePrivate() {
  const btn = $("priv");
  const show = async () => {
    try {
      const out = await (await fetch("/api/backend")).json();
      const on = out.backend === "baseten";
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on);
    } catch (err) { /* offline page, leave default */ }
  };
  btn.onclick = async () => {
    const on = btn.getAttribute("aria-pressed") !== "true";
    try {
      await fetch("/api/backend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backend: on ? "baseten" : "meta" }),
      });
    } catch (err) { /* offline page, visual only */ }
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on);
  };
  await show();
}

function log(signalKind, strategy, reason) {
  state.timeline.unshift({ signal: signalKind, strategy, reason });
  const tl = $("timeline");
  tl.innerHTML = "";
  state.timeline.forEach((t) => {
    const li = document.createElement("li");
    li.textContent = `${t.signal} → ${t.strategy}: ${t.reason}`;
    tl.appendChild(li);
  });
}

window.addEventListener("resize", sizeOverlay);
init();
