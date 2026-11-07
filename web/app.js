const $ = (id) => document.getElementById(id);
const log = $("log"), input = $("input"), send = $("send"), welcome = $("welcome");
const KEY = "risa-chat";
let history = [];
let busy = false;

function save() {
  try { sessionStorage.setItem(KEY, JSON.stringify(history)); } catch (_) {}
}
function load() {
  try { history = JSON.parse(sessionStorage.getItem(KEY)) || []; } catch (_) { history = []; }
}

const hhmm = () => new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
const DOWNLOAD = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 4v10m0 0-4-4m4 4 4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const size = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

function div(cls, text) {
  const el = document.createElement("div");
  el.className = cls;
  if (text != null) el.textContent = text;
  return el;
}

// one row = optional avatar + bubble + time stamp (shown on hover)
function row(role, bubble, time) {
  const r = div(`row ${role}`), stack = div("stack");
  stack.append(bubble, div("time", time));
  if (role === "bot") r.append(div("avatar", "RiSA"));
  r.append(stack);
  log.append(r);
  log.scrollTop = log.scrollHeight;
  return r;
}

function card(f) {
  const a = document.createElement("a");
  a.className = "fcard";
  a.href = `/download/${encodeURIComponent(f.id)}`;
  const body = div("fbody");
  body.append(div("fname", f.name));
  if (f.summary) body.append(div("fsum", f.summary));
  const type = f.name.split(".").pop().toUpperCase();
  body.append(div("fmeta", f.size == null ? type : `${type} · ${size(f.size)}`));
  const dl = document.createElement("span");
  dl.className = "fdl";
  dl.innerHTML = DOWNLOAD;
  a.append(fileIcon(f.name), body, dl);
  return a;
}

function add(role, text, files = [], err = false, time = hhmm()) {
  welcome.classList.add("hidden");
  const el = div(`msg ${role === "user" ? "user" : "bot"}${err ? " err" : ""}`, text);
  if (files.length) {
    const cards = div("cards");
    cards.append(...files.map(card));
    el.append(cards);
  }
  return row(role === "user" ? "user" : "bot", el, time);
}

const SPARK = '<svg class="spark" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2l1.9 7.1L21 11l-7.1 1.9L12 20l-1.9-7.1L3 11l7.1-1.9z"/></svg>';

// shows what the server is doing ("status" lines) until the first word of the answer arrives
function typing() {
  const el = div("msg bot"), status = document.createElement("span"), label = document.createElement("span");
  status.className = "waiting";
  status.innerHTML = SPARK;
  label.className = "shimmer";
  status.append(label);
  el.append(status);
  label.textContent = "กำลังคิด...";
  const r = row("bot", el, "");
  return { remove: () => r.remove(), set: (t) => { label.textContent = t; } };
}

async function ask(message) {
  message = message.trim();
  if (!message || busy) return;
  busy = true; send.disabled = true;
  input.value = ""; resize();
  add("user", message);
  const wait = typing();
  let bubble = null, text = "";  // the bot row while its answer streams in
  const fail = (msg) => { wait.remove(); bubble?.remove(); add("bot", msg, [], true); };
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history.slice(-12) }),
    });
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      return fail(data.text || "ขออภัย ส่งคำถามไม่สำเร็จ กรุณาลองใหม่อีกครั้ง");
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "", done = null, error = null;
    const show = () => {
      if (!text && !bubble) return;
      if (!bubble) { wait.remove(); bubble = add("bot", ""); }
      bubble.querySelector(".msg").textContent = text;
      log.scrollTop = log.scrollHeight;
    };
    for (;;) {
      const { value, done: end } = await reader.read();
      if (end) break;
      buf += dec.decode(value, { stream: true });
      for (let i; (i = buf.indexOf("\n")) >= 0; buf = buf.slice(i + 1)) {
        const ev = JSON.parse(buf.slice(0, i));
        if (ev.status) wait.set(ev.status);
        else if ("delta" in ev) { text = ev.delta === null ? "" : text + ev.delta; show(); }
        else if (ev.done) done = ev;
        else if (ev.error) error = ev.error;
      }
    }
    if (!done) return fail(error || "ขออภัย เชื่อมต่อระบบไม่ได้ กรุณาลองใหม่อีกครั้ง");
    wait.remove();
    if (bubble) {  // the final text can differ from what streamed (marker or language fix): replace it, then add the file cards
      const el = bubble.querySelector(".msg");
      el.textContent = done.text;
      if (done.files?.length) { const cards = div("cards"); cards.append(...done.files.map(card)); el.append(cards); }
    } else add("bot", done.text, done.files || []);
    // the model only sees text, so name the files that were sent: "the other one" then has something to refer to
    const sent = (done.files || []).map((f) => f.name).join(", ");
    history.push({ role: "user", content: message }, { role: "assistant", content: sent ? `${done.text} [ส่งไฟล์: ${sent}]` : done.text });
    save();
  } catch (_) {
    fail("ขออภัย เชื่อมต่อระบบไม่ได้ กรุณาลองใหม่อีกครั้ง");
  } finally {
    busy = false; send.disabled = false; input.focus();
  }
}

function resize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
input.addEventListener("input", resize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); }
});
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => ask(c.textContent)));
$("new").addEventListener("click", () => {
  history = []; save();
  const reset = () => {
    log.querySelectorAll(".row").forEach((m) => m.remove());
    welcome.classList.remove("hidden");
  };
  document.startViewTransition ? document.startViewTransition(reset) : reset();
  input.focus();
});

if (window.self !== window.top) document.documentElement.classList.add("embedded");  // shown inside the researcher drawer
load();
// restore earlier turns after a page refresh (file cards and time stamps are not restored)
for (const t of history) add(t.role, t.content, [], false, "");
input.focus();
