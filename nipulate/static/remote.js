"use strict";

// ---- settings and storage -------------------------------------------------

const TWO_TAP_MS = 400;      // two fingers down and up within this, without moving: right-click
const HOLD_MS = 450;         // a touch held still this long starts a drag
const SLOP_PX = 8;           // movement below this still counts as holding still
const REPEAT_DELAY_MS = 400; // held volume/arrow keys start repeating after this
const REPEAT_EVERY_MS = 110;
const PING_EVERY_MS = 2000;
const PONG_TIMEOUT_MS = 6000;

const $ = (s) => document.querySelector(s);
const store = {
  get(k, d = null) { try { const v = localStorage.getItem("nipulate." + k); return v === null ? d : v; } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem("nipulate." + k, v); } catch (_) {} },
  del(k) { try { localStorage.removeItem("nipulate." + k); } catch (_) {} },
};

const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const standalone = navigator.standalone === true ||
  matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches;

function randomId() {
  const a = new Uint8Array(12);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

let clientId = store.get("id");
if (!clientId) { clientId = randomId(); store.set("id", clientId); }

// Older versions paired with a key in the address (#k=...). Nothing to pair now: tidy it away.
if (location.hash) history.replaceState(null, "", location.pathname + location.search);
store.del("token");

let sensitivity = parseFloat(store.get("sens", "1.5")) || 1.5;
let natural = store.get("natural", "1") === "1";

// ---- connection -----------------------------------------------------------

let ws = null;
let authed = false;
let reconnect = true;     // false while another tab has taken over
let backoff = 500;
let reconnectTimer = 0;
let lastPong = 0;
let latency = null;

function send(obj) {
  if (ws && authed && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function setStatus(text, kind) {
  $("#status").textContent = text;
  $("#dot").className = kind || "";
}

function connect() {
  clearTimeout(reconnectTimer);
  if (ws && ws.readyState <= WebSocket.OPEN) return;
  setStatus("Connecting", "wait");
  const sock = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws = sock;
  sock.onopen = () => {
    lastPong = performance.now();
    sock.send(JSON.stringify({ t: "hello", id: clientId, standalone }));
  };
  sock.onmessage = (e) => { if (sock === ws) onMessage(JSON.parse(e.data)); };
  sock.onclose = () => { if (sock === ws) dropped(); };
  sock.onerror = () => {};
}

function dropped() {
  const was = ws;
  ws = null;
  authed = false;
  releaseHeld(false);
  try { was && was.close(); } catch (_) {}
  if (!reconnect) return;
  setStatus(navigator.onLine === false ? "Offline" : "Reconnecting", "wait");
  reconnectTimer = setTimeout(connect, backoff);
  backoff = Math.min(backoff * 1.6, 4000);
}

function onMessage(msg) {
  switch (msg.t) {
    case "ok":
      authed = true;
      backoff = 500;
      setStatus("Connected", "ok");
      send({ t: "set", sens: sensitivity });
      if (msg.vol) showVolume(msg.vol.level, msg.vol.muted);
      $("#version").textContent = "nipulate " + (msg.version || "");
      break;
    case "pong":
      lastPong = performance.now();
      latency = Math.round(performance.now() - msg.ping);
      break;
    case "vol":
      showVolume(msg.level, msg.muted);
      break;
    case "replaced":
      reconnect = false;
      setStatus("Paused", "");
      show("#replaced");
      break;
  }
}

// Heartbeat: measures latency, and notices a dead connection faster than the browser does.
setInterval(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN || !authed) return;
  if (performance.now() - lastPong > PONG_TIMEOUT_MS) { dropped(); return; }
  send({ t: "ping", ping: performance.now(), lat: latency });
}, PING_EVERY_MS);

addEventListener("online", () => { if (!ws && reconnect) connect(); });

// ---- overlays ---------------------------------------------------------------

function show(sel) { $(sel).hidden = false; }
function hide(sel) { $(sel).hidden = true; }

$("#take-over").addEventListener("click", () => {
  hide("#replaced");
  reconnect = true;
  backoff = 500;
  connect();
});

// ---- volume display -----------------------------------------------------------

function showVolume(level, muted) {
  $("#level").textContent = level;
  $("#level-bar").hidden = false;
  $("#level-fill").style.width = level + "%";
  $("#mute").classList.toggle("muted", !!muted);
  $("#mute-icon use").setAttribute("href", muted ? "#i-muted" : "#i-speaker");
}

// ---- buttons ------------------------------------------------------------------

let repeatTimer = 0;
let repeatKey = null;
const pressed = new Map(); // pointerId -> button element

function stopRepeat() {
  clearTimeout(repeatTimer);
  clearInterval(repeatTimer);
  repeatTimer = 0;
  repeatKey = null;
}

document.addEventListener("pointerdown", (e) => {
  const btn = e.target.closest("[data-key]");
  if (!btn) return;
  e.preventDefault();
  const key = btn.dataset.key;
  btn.classList.add("on");
  pressed.set(e.pointerId, btn);
  send({ t: "key", k: key });
  if (btn.hasAttribute("data-repeat")) {
    stopRepeat();
    repeatKey = key;
    repeatTimer = setTimeout(() => {
      repeatTimer = setInterval(() => send({ t: "key", k: repeatKey }), REPEAT_EVERY_MS);
    }, REPEAT_DELAY_MS);
  }
});

function unpress(e) {
  const btn = pressed.get(e.pointerId);
  if (!btn) return;
  pressed.delete(e.pointerId);
  btn.classList.remove("on");
  if (btn.dataset.key === repeatKey) stopRepeat();
}
document.addEventListener("pointerup", unpress);
document.addEventListener("pointercancel", unpress);

// ---- trackpad -------------------------------------------------------------------

const pad = $("#pad");
const touches = new Map(); // pointerId -> {x, y, sx, sy}
let mode = "idle";         // idle | pending | move | drag | two | scroll | done
let t0 = 0;
let twoMoved = 0;
let holdTimer = 0;
let pendX = 0, pendY = 0, scrollX = 0, scrollY = 0;
let frameQueued = false;
let lastFrame = 0;

function queueFrame() {
  if (frameQueued) return;
  frameQueued = true;
  requestAnimationFrame(flush);
  setTimeout(() => { if (frameQueued) flush(performance.now()); }, 50); // in case frames stall
}

// Movement is added up and sent once per animation frame; clicks go out immediately.
function flush(ts) {
  frameQueued = false;
  const dt = ts - lastFrame > 100 ? 16 : Math.max(1, ts - lastFrame);
  lastFrame = ts;
  if (pendX || pendY) {
    send({ t: "m", dx: +pendX.toFixed(2), dy: +pendY.toFixed(2), dt: +dt.toFixed(1) });
    pendX = pendY = 0;
  }
  if (scrollX || scrollY) {
    // Lock to the main axis so vertical scrolling doesn't drift sideways.
    let sx = scrollX, sy = scrollY;
    if (Math.abs(sx) < Math.abs(sy) * 0.5) sx = 0; else if (Math.abs(sy) < Math.abs(sx) * 0.5) sy = 0;
    const k = natural ? -1 : 1; // natural: content follows the fingers
    send({ t: "scroll", dx: +(sx * k).toFixed(2), dy: +(sy * k).toFixed(2) });
    scrollX = scrollY = 0;
  }
}

function startDrag() {
  if (mode !== "pending") return;
  mode = "drag";
  pad.classList.add("dragging");
  send({ t: "button", b: "left", a: "down" });
}

function padReset() {
  clearTimeout(holdTimer);
  touches.clear();
  mode = "idle";
  pendX = pendY = scrollX = scrollY = 0;
  pad.classList.remove("dragging", "scrolling");
}

pad.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  try { pad.setPointerCapture(e.pointerId); } catch (_) {}
  pad.classList.add("used");
  touches.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY });
  if (touches.size === 1) {
    mode = "pending";
    t0 = performance.now();
    holdTimer = setTimeout(startDrag, HOLD_MS);
  } else if (touches.size === 2 && (mode === "pending" || mode === "move")) {
    clearTimeout(holdTimer);
    mode = "two";
    t0 = performance.now();
    twoMoved = 0;
  } else if (touches.size > 2 && mode !== "drag") {
    mode = "done"; // three or more fingers: ignore until everyone lifts
  }
});

pad.addEventListener("pointermove", (e) => {
  const t = touches.get(e.pointerId);
  if (!t) return;
  const dx = e.clientX - t.x, dy = e.clientY - t.y;
  t.x = e.clientX; t.y = e.clientY;
  if (mode === "pending") {
    if (Math.hypot(t.x - t.sx, t.y - t.sy) > SLOP_PX) {
      clearTimeout(holdTimer);
      mode = "move";
      pendX += t.x - t.sx; pendY += t.y - t.sy; // include the slop, so small moves aren't swallowed
      queueFrame();
    }
  } else if (mode === "move" || mode === "drag") {
    pendX += dx; pendY += dy;
    queueFrame();
  } else if (mode === "two" || mode === "scroll") {
    // Each event moves one finger; the midpoint of two fingers moves half as far.
    scrollX += dx / 2; scrollY += dy / 2;
    twoMoved += Math.hypot(dx, dy) / 2;
    if (mode === "two" && twoMoved > SLOP_PX) { mode = "scroll"; pad.classList.add("scrolling"); }
    if (mode === "scroll") queueFrame(); else { scrollX = scrollY = 0; }
  }
});

function padUp(e) {
  if (!touches.delete(e.pointerId)) return;
  flush(performance.now()); // send the last bit of movement before any button change
  const elapsed = performance.now() - t0;
  switch (mode) {
    case "pending": // one finger, didn't move: a tap (or a long press without moving)
      if (touches.size === 0) send({ t: "button", b: "left", a: "click" });
      break;
    case "drag":
      if (touches.size === 0) send({ t: "button", b: "left", a: "up" });
      break;
    case "two": // first of two fingers lifted
      if (elapsed < TWO_TAP_MS) {
        if (touches.size === 0) send({ t: "button", b: "right", a: "click" });
        else mode = "twoUp"; // wait for the other finger
      } else {
        mode = "done";
      }
      break;
    case "twoUp":
      if (touches.size === 0 && elapsed < TWO_TAP_MS) send({ t: "button", b: "right", a: "click" });
      break;
    case "move":
    case "scroll":
      mode = "done"; // a finger lifted mid-gesture: don't let the other start something new
      break;
  }
  if (touches.size === 0) padReset();
}
pad.addEventListener("pointerup", padUp);
pad.addEventListener("pointercancel", padUp);
document.addEventListener("contextmenu", (e) => e.preventDefault());
document.addEventListener("gesturestart", (e) => e.preventDefault());
document.addEventListener("dblclick", (e) => e.preventDefault());

// Let go of anything held when the page loses focus or the connection drops.
function releaseHeld(tellServer = true) {
  const dragging = mode === "drag";
  padReset();
  stopRepeat();
  for (const btn of pressed.values()) btn.classList.remove("on");
  pressed.clear();
  if (tellServer && dragging) send({ t: "button", b: "left", a: "up" });
  if (tellServer) send({ t: "release" });
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) releaseHeld();
  else if (!ws && reconnect) { backoff = 500; connect(); }
});
addEventListener("blur", () => releaseHeld());
addEventListener("pagehide", () => releaseHeld());

// ---- keyboard ---------------------------------------------------------------------

// The phone keyboard types into a hidden field. It always holds a few invisible characters,
// so Backspace on an "empty" field still produces an input event. Each change is diffed
// against the previous value: removed characters become Backspace, new ones become text.
// This copes with autocorrect and with keyboards that rewrite the whole word as you type.
const kbd = $("#kbd");
const SENTINEL = "​​​​";
let prevValue = SENTINEL;
let composing = false;
let typedEcho = "";

function resetField() {
  kbd.value = SENTINEL;
  prevValue = SENTINEL;
  try { kbd.setSelectionRange(SENTINEL.length, SENTINEL.length); } catch (_) {}
}

function echo(text, erase) {
  if (erase) typedEcho = Array.from(typedEcho).slice(0, -erase).join("");
  typedEcho = (typedEcho + text).slice(-40);
  const el = $("#typed");
  el.textContent = typedEcho;
  el.hidden = false;
  $("#status").hidden = true;
}

kbd.addEventListener("input", () => {
  const before = Array.from(prevValue);
  const after = Array.from(kbd.value);
  let i = 0;
  while (i < before.length && i < after.length && before[i] === after[i]) i++;
  const removed = before.length - i;
  const added = after.slice(i).join("").replace(/​/g, "");
  for (let n = 0; n < removed; n++) send({ t: "key", k: "backspace" });
  if (added) {
    const lines = added.split("\n");
    lines.forEach((line, n) => {
      if (n) send({ t: "key", k: "enter" });
      if (line) send({ t: "text", s: line });
    });
  }
  echo(added, removed);
  prevValue = kbd.value;
  if (!composing && (!kbd.value.startsWith(SENTINEL) || kbd.value.length > 64)) resetField();
});
kbd.addEventListener("compositionstart", () => { composing = true; });
kbd.addEventListener("compositionend", () => {
  composing = false;
  if (!kbd.value.startsWith(SENTINEL) || kbd.value.length > 64) resetField();
});
kbd.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    send({ t: "key", k: "enter" });
    echo("↵");
    resetField();
  }
});

function keyboardOpen() { return document.activeElement === kbd; }

function setKeyboardUi(open) {
  $("#kbd-btn").classList.toggle("active", open);
  if (!open) {
    $("#typed").hidden = true;
    $("#status").hidden = false;
    typedEcho = "";
  }
}

$("#kbd-btn").addEventListener("pointerdown", (e) => e.preventDefault()); // keep focus where it is
$("#kbd-btn").addEventListener("click", () => {
  if (keyboardOpen()) {
    kbd.blur();
  } else {
    resetField();
    kbd.focus(); // must happen inside the tap for the phone to show its keyboard
  }
});
kbd.addEventListener("focus", () => setKeyboardUi(true));
kbd.addEventListener("blur", () => setKeyboardUi(false));

// ---- special-keys drawer ---------------------------------------------------------------

function setDrawer(open) {
  $("#drawer").classList.toggle("open", open);
  $("#drawer").setAttribute("aria-hidden", String(!open));
  $("#keys-btn").classList.toggle("active", open);
  $("#keys-btn").setAttribute("aria-expanded", String(open));
}
$("#keys-btn").addEventListener("click", () => setDrawer(!$("#drawer").classList.contains("open")));
pad.addEventListener("pointerdown", () => setDrawer(false));

$("#lock-btn").addEventListener("click", () => show("#confirm-lock"));
$("#lock-cancel").addEventListener("click", () => hide("#confirm-lock"));
$("#lock-ok").addEventListener("click", () => {
  hide("#confirm-lock");
  setDrawer(false);
  send({ t: "lock" });
});

// ---- settings ------------------------------------------------------------------------------

function renderSettings() {
  $("#sens").value = sensitivity;
  $("#sens-value").textContent = sensitivity.toFixed(1) + "x";
  for (const b of document.querySelectorAll("#scroll-dir button")) {
    b.classList.toggle("sel", (b.dataset.natural === "1") === natural);
  }
  $("#scroll-help").textContent = natural
    ? "The page moves with your fingers, like a phone."
    : "Like a mouse wheel: fingers down scrolls down.";
  $("#ios-tip").hidden = !(isIOS && !standalone);
}

$("#open-settings").addEventListener("click", () => { renderSettings(); show("#settings"); });
$("#settings-done").addEventListener("click", () => hide("#settings"));
$("#settings").addEventListener("click", (e) => { if (e.target.id === "settings") hide("#settings"); });
$("#sens").addEventListener("input", (e) => {
  sensitivity = parseFloat(e.target.value);
  store.set("sens", String(sensitivity));
  renderSettings();
  send({ t: "set", sens: sensitivity });
});
for (const b of document.querySelectorAll("#scroll-dir button")) {
  b.addEventListener("click", () => {
    natural = b.dataset.natural === "1";
    store.set("natural", natural ? "1" : "0");
    renderSettings();
  });
}
// ---- start --------------------------------------------------------------------------------

connect();
