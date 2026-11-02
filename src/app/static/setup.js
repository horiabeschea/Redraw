"use strict";
/* Parent setup: everything stays in localStorage ("redraw.settings");
 * the lesson screen reads it on load. Only the backend choice is sent
 * to the server. */
const KEY = "redraw.settings";
const DEFAULTS = { name: "", age: "7–8", level: "medium", terms: 1,
  worlds: ["dino", "block"], own: "", mode: "meta",
  toggles: { calm: true, timers: true, large: true, read: true, motion: true } };

const LEVELS = [
  { id: "short", label: "Short", hint: "up to 6 words", longest: 6,
    text: "Warm air goes up. Up high it cools. Drops make a cloud." },
  { id: "medium", label: "Medium", hint: "up to 10 words", longest: 10,
    text: "Up high the air is cold. The vapor turns into tiny drops. Tiny drops make a cloud." },
  { id: "longer", label: "Longer", hint: "up to 14 words", longest: 14,
    text: "Higher up, cool air turns the vapor back into tiny drops of water." },
];
const WORLDS = [
  { id: "dino", label: "Dinosaurs" }, { id: "block", label: "Block worlds" },
  { id: "space", label: "Space", soon: true },
  { id: "ocean", label: "Ocean", soon: true },
  { id: "trains", label: "Trains", soon: true },
  { id: "robots", label: "Robots", soon: true },
];
const TOGGLES = [
  { id: "calm", label: "Calm colours", hint: "Soft palette, no bright flashes" },
  { id: "timers", label: "No timers", hint: "Nothing counts down on screen" },
  { id: "large", label: "Large text", hint: "Bigger captions and buttons" },
  { id: "read", label: "Read aloud by default", hint: "Captions are spoken for you" },
  { id: "motion", label: "Reduce motion", hint: "Pictures change without animation" },
];
const MODES = [
  { id: "meta", label: "Standard",
    hint: "Uses Meta’s hosted models. Your content is not used to train them." },
  { id: "baseten", label: "Private mode",
    hint: "Uses an open-weight model. Spoken answers are not sent to a closed service." },
];

const $ = (id) => document.getElementById(id);
let s;
try { s = Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY))); }
catch (err) { s = Object.assign({}, DEFAULTS); }

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (err) { /* private window */ }
  render();
}

function choices(box, items, isOn, onPick, cls) {
  box.innerHTML = "";
  items.forEach((it) => {
    const b = document.createElement("button");
    b.className = cls;
    b.setAttribute("aria-pressed", isOn(it));
    b.textContent = it.label;
    if (it.hint) {
      const small = document.createElement("small");
      small.textContent = it.hint;
      if (cls === "mode") { b.textContent = ""; const t = document.createElement("b");
        t.textContent = it.label; b.appendChild(t); }
      b.appendChild(small);
    }
    b.onclick = () => onPick(it);
    box.appendChild(b);
  });
}

function render() {
  choices($("ages"), ["5–6", "7–8", "9–10"].map((a) => ({ id: a, label: a })),
    (a) => s.age === a.id, (a) => { s.age = a.id; save(); }, "choice");
  choices($("levels"), LEVELS, (l) => s.level === l.id,
    (l) => { s.level = l.id; save(); }, "choice");
  choices($("terms"), [{ id: 1, label: "1 (gentlest)" }, { id: 2, label: "2" }],
    (t) => s.terms === t.id, (t) => { s.terms = t.id; save(); }, "choice");
  choices($("worlds"), WORLDS.filter((w) => !w.soon),
    (w) => s.worlds.includes(w.id), (w) => {
      if (s.worlds.includes(w.id)) s.worlds = s.worlds.filter((x) => x !== w.id);
      else if (s.worlds.length < 3) s.worlds = s.worlds.concat([w.id]);
      save();
    }, "pill");
  const soon = $("soonworlds");
  if (soon) soon.textContent = WORLDS.filter((w) => w.soon)
    .map((w) => w.label).join(", ") + " — coming soon";
  const own = ($("ownworld").value || "").trim();
  const note = $("ownnote");
  if (note) note.textContent = own
    ? `“${own}” is saved for later — lessons in new worlds arrive with the Lesson Builder.`
    : "";
  choices($("modes"), MODES, (m) => s.mode === m.id, (m) => {
    s.mode = m.id; save();
    fetch("/api/backend", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend: m.id }) }).catch(() => {});
  }, "mode");

  const tg = $("toggles");
  tg.innerHTML = "";
  TOGGLES.forEach((t) => {
    const row = document.createElement("div");
    row.className = "toggle-row";
    const txt = document.createElement("div");
    const b = document.createElement("b"); b.textContent = t.label;
    const small = document.createElement("small"); small.textContent = t.hint;
    txt.append(b, small);
    const sw = document.createElement("button");
    sw.className = "switch";
    sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", !!s.toggles[t.id]);
    sw.setAttribute("aria-label", t.label);
    sw.onclick = () => { s.toggles = Object.assign({}, s.toggles,
      { [t.id]: !s.toggles[t.id] }); save(); };
    row.append(txt, sw);
    tg.appendChild(row);
  });

  const names = WORLDS.filter((w) => s.worlds.includes(w.id)).map((w) => w.label);
  $("worldnames").textContent = names.length ? names.join(", ") : "none picked yet";
  const cur = LEVELS.find((l) => l.id === s.level) || LEVELS[1];
  $("sample").textContent = cur.text;
  $("samplenote").textContent = `Longest sentence: ${cur.longest} words · ` +
    (s.terms === 1 ? "1 new word per step" : "2 new words per step");
}

$("childname").value = s.name;
$("ownworld").value = s.own;
$("childname").oninput = (e) => { s.name = e.target.value; save(); };
$("ownworld").oninput = (e) => { s.own = e.target.value; save(); };
// Show the server's current backend rather than a stale local choice.
/* Parent report: built on demand from the lesson page's local snapshot
 * ("redraw.session"). Only aggregates reach the server; rendered text
 * uses textContent, never innerHTML. */
const SESSION_KEY = "redraw.session";
function loadSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; }
  catch (err) { return null; }
}
function updateReportNote() {
  const snap = loadSession();
  const note = $("reportnote"), btn = $("reportbtn");
  if (!snap || !(snap.entries || []).length) {
    note.textContent = "No lesson yet on this device — run the water-cycle lesson first.";
    btn.disabled = true;
    return;
  }
  const when = snap.saved_at ? new Date(snap.saved_at).toLocaleString() : "";
  note.textContent = `Builds from the last lesson on this device${when ? ` (${when})` : ""}. One short model call; offline it falls back to a plain summary.`;
  btn.disabled = false;
}
function renderReport(r, ms, fallback) {
  const out = $("reportout");
  out.innerHTML = "";
  const add = (title, items) => {
    if (!items || !items.length) return;
    const h = document.createElement("div");
    h.className = "field-label";
    h.style.fontSize = "13px";
    h.textContent = title;
    out.appendChild(h);
    const ul = document.createElement("ul");
    items.forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t;
      ul.appendChild(li);
    });
    out.appendChild(ul);
  };
  const meta = document.createElement("div");
  meta.className = "hint";
  meta.textContent = fallback
    ? "Offline summary (no model call)."
    : `Written just now${ms != null ? ` in ${(ms / 1000).toFixed(1)}s` : ""}.`;
  out.appendChild(meta);
  add("Concepts mastered", r.mastered_concepts);
  add("Where extra explanations helped", (r.stuck_steps || [])
    .filter((st) => st.stuck_signals > 0 || st.support_flag !== "none")
    .map((st) => `Step ${st.step} (${st.concept}): ${st.stuck_signals} extra ` +
      `explanation${st.stuck_signals === 1 ? "" : "s"}` +
      (st.support_flag !== "none" ? "; explored with a grown-up" : "")));
  add("Worlds that clicked", (r.world_fit || [])
    .filter((w) => w.checks_total > 0)
    .map((w) => `${w.world}: ${w.checks_passed}/${w.checks_total} checks`));
  add("Strengths", r.strengths);
  add("Growing edges", r.growth_areas);
  add("Try at home", r.try_at_home);
}
/* Lesson Builder: topic + facts -> Wonder core -> parent review ->
 * versioned pack -> scenes. Long builds run server-side; this page only
 * starts them and renders the result. Model text uses textContent only. */
const PACK_WORLDS = { dino: "dinosaur_valley", block: "block_world" };
function packSlugFor(topic) {
  const slug = String(topic || "").toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "").slice(0, 40);
  return slug || "custom-lesson";
}
function buildWorlds() {
  const ids = (s.worlds || []).map((w) => PACK_WORLDS[w]).filter(Boolean);
  return ids.length ? ids : ["dinosaur_valley", "block_world"];
}
async function refreshPacks() {
  const box = $("packlist");
  box.innerHTML = "";
  let packs = [];
  try {
    packs = (await (await fetch("/api/packs")).json()).packs || [];
  } catch (err) { /* server down: list stays empty */ }
  let current = null;
  try { current = localStorage.getItem("redraw.pack") || "water-cycle"; }
  catch (err) { current = "water-cycle"; }
  packs.forEach((p) => {
    const row = document.createElement("div");
    row.className = "lesson-row";
    row.textContent = `${p.topic} · ${p.steps} steps · v${p.version}`;
    const use = document.createElement("button");
    use.className = "outline";
    use.textContent = p.slug === current ? "In use" : "Use";
    use.disabled = p.slug === current;
    use.onclick = () => {
      try { localStorage.setItem("redraw.pack", p.slug); } catch (err) {}
      refreshPacks();
    };
    row.appendChild(use);
    box.appendChild(row);
  });
  if (!packs.length) {
    box.textContent = "Water cycle only — build a topic to add more.";
  }
}
function renderReview(pack, verdicts) {
  const out = $("buildout");
  out.innerHTML = "";
  const verdict = document.createElement("div");
  verdict.className = "hint";
  const bad = (verdicts || []).filter((v) => v.accurate === "no");
  verdict.textContent = bad.length
    ? `Checker flagged ${bad.length} step(s) — read them carefully before saving.`
    : "Science check passed on every step. Adjust any wording, then save.";
  out.appendChild(verdict);
  pack.steps.forEach((st, i) => {
    const wrap = document.createElement("div");
    wrap.style.marginTop = "10px";
    const h = document.createElement("div");
    h.className = "field-label";
    h.style.fontSize = "13px";
    h.textContent = `Step ${st.step}: ${st.step_name}`;
    wrap.appendChild(h);
    [["caption", st.caption], ["simpler_caption", st.simpler_caption]]
      .forEach(([field, text]) => {
        const ta = document.createElement("textarea");
        ta.className = "text";
        ta.rows = 2;
        ta.dataset.step = String(i);
        ta.dataset.field = field;
        ta.value = text;
        ta.style.cssText = "width: 100%; margin-top: 6px; font-size: 14px; padding: 8px 10px";
        wrap.appendChild(ta);
      });
    const tap = document.createElement("div");
    tap.className = "hint";
    tap.textContent = `Tap check: ${st.tap_question.prompt} → ${st.tap_question.target_noun}`;
    wrap.appendChild(tap);
    out.appendChild(wrap);
  });
  const row = document.createElement("div");
  row.style.cssText = "display: flex; gap: 8px; margin-top: 10px";
  const save = document.createElement("button");
  save.className = "outline";
  save.textContent = "Save this lesson";
  save.onclick = () => savePack(pack);
  row.appendChild(save);
  const scenes = document.createElement("button");
  scenes.className = "outline";
  scenes.textContent = "Build scenes";
  scenes.onclick = () => buildScenes(pack);
  row.appendChild(scenes);
  out.appendChild(row);
  const note = document.createElement("div");
  note.className = "hint";
  note.id = "savenote";
  out.appendChild(note);
  out.dataset.slug = pack.slug;
}
async function savePack(pack) {
  const note = $("savenote");
  const edited = JSON.parse(JSON.stringify(pack));
  document.querySelectorAll("#buildout textarea").forEach((ta) => {
    edited.steps[Number(ta.dataset.step)][ta.dataset.field] = ta.value;
  });
  note.textContent = "Saving and re-checking the science…";
  try {
    const slug = edited.slug;
    const saved = await (await fetch(`/api/packs/${slug}`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pack: edited }) })).json();
    if (saved.error) throw new Error(saved.error);
    edited.version = saved.version;
    const ver = await (await fetch("/api/verify", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug }) })).json();
    if (ver.error) throw new Error(ver.error);
    const bad = (ver.verdicts || []).filter((v) => v.accurate === "no");
    note.textContent = bad.length
      ? `Saved as v${saved.version}, but the checker flagged ${bad.length} step(s).`
      : `Saved as v${saved.version}; science check passed.`;
    await refreshPacks();
  } catch (err) {
    note.textContent = `Could not save: ${err.message || err}`;
  }
}
async function buildScenes(pack) {
  const note = $("savenote") || $("buildnote");
  note.textContent = "Building scenes — step 1 first, then the rest. This takes a few minutes.";
  try {
    const res = await (await fetch("/api/build-scenes", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: pack.slug, worlds: buildWorlds() }) })).json();
    if (res.error) throw new Error(res.error);
    const lines = (res.scenes || []).map((sc) =>
      `step ${sc.step} ${sc.world}: ${sc.method}, ${sc.sam}`);
    note.textContent = lines.length ? lines.join(" · ") : "No scenes built.";
  } catch (err) {
    note.textContent = `Scene build failed: ${err.message || err}`;
  }
}
$("buildbtn").onclick = async () => {
  const topic = ($("topic").value || "").trim();
  const facts = ($("topicfacts").value || "").split("\n")
    .map((f) => f.trim()).filter(Boolean);
  const note = $("buildnote");
  if (s.mode !== "meta") {
    note.textContent = "Lesson building needs Standard mode — the open-weights backend has no lesson writer.";
    return;
  }
  if (!topic || facts.length < 3) {
    note.textContent = "Give a topic and at least 3 facts (one per line).";
    return;
  }
  const btn = $("buildbtn");
  btn.disabled = true;
  note.textContent = "Muse Wonder is writing the lesson (one call), then checking it (one more)…";
  try {
    const res = await (await fetch("/api/build-core", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: packSlugFor(topic), topic, facts,
        worlds: buildWorlds(),
        profile: { age: s.age, level: s.level, terms: s.terms } }) })).json();
    if (res.error) throw new Error(res.error);
    note.textContent = res.cached
      ? "Rebuilt from cache — review the wording below."
      : "Fresh lesson built — review every step before your child sees it.";
    renderReview(res.pack, res.verdicts);
    await refreshPacks();
  } catch (err) {
    note.textContent = `Build failed: ${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
};
refreshPacks();
$("reportbtn").onclick = async () => {
  const snap = loadSession();
  if (!snap) { updateReportNote(); return; }
  const btn = $("reportbtn");
  btn.disabled = true;
  $("reportnote").textContent = "Writing the report…";
  try {
    const res = await fetch("/api/report", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entries: snap.entries, mastered: snap.mastered,
        current_step: snap.current_step, concepts: snap.concepts,
        profile: { age: s.age, level: s.level, terms: s.terms } }) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const out = await res.json();
    renderReport(out.result, out.ms, out.fallback);
    $("reportnote").textContent = "Built from the last lesson on this device.";
  } catch (err) {
    $("reportnote").textContent = "Could not reach the server. Start it and try again.";
  } finally {
    btn.disabled = false;
  }
};
updateReportNote();
fetch("/api/backend").then((r) => r.json())
  .then((out) => { s.mode = out.backend; render(); }).catch(() => {});
render();
