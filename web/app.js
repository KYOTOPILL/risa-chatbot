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

// the model's steps are not streamed, so the status text just rotates while it works
const WAITING = ["กำลังค้นหาเอกสาร", "กำลังหาไฟล์", "กำลังเตรียมคำตอบ"];
function typing() {
  const el = div("msg bot"), status = document.createElement("span"), label = document.createElement("span");
  status.className = "waiting";
  status.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  status.append(label);
  el.append(status);
  let i = 0;
  const tick = () => { label.textContent = WAITING[i++ % WAITING.length] + "..."; };
  tick();
  const r = row("bot", el, "");
  const timer = setInterval(tick, 1800);
  return { remove: () => { clearInterval(timer); r.remove(); } };
}

async function ask(message) {
  message = message.trim();
  if (!message || busy) return;
  busy = true; send.disabled = true;
  input.value = ""; resize();
  add("user", message);
  const wait = typing();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history.slice(-12) }),
    });
    const data = await res.json().catch(() => ({}));
    wait.remove();
    if (!res.ok) {
      add("bot", data.text || "ขออภัย ส่งคำถามไม่สำเร็จ กรุณาลองใหม่อีกครั้ง", [], true);
    } else {
      add("bot", data.text, data.files || []);
      // the model only sees text, so name the files that were sent: "the other one" then has something to refer to
      const sent = (data.files || []).map((f) => f.name).join(", ");
      history.push({ role: "user", content: message }, { role: "assistant", content: sent ? `${data.text} [ส่งไฟล์: ${sent}]` : data.text });
      save();
    }
  } catch (_) {
    wait.remove();
    add("bot", "ขออภัย เชื่อมต่อระบบไม่ได้ กรุณาลองใหม่อีกครั้ง", [], true);
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

load();
// restore earlier turns after a page refresh (file cards and time stamps are not restored)
for (const t of history) add(t.role, t.content, [], false, "");
input.focus();
