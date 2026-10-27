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
fetch("/api/backend").then((r) => r.json())
  .then((out) => { s.mode = out.backend; render(); }).catch(() => {});
render();
