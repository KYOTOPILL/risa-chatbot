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

function add(role, text, files = [], err = false) {
  welcome.classList.add("hidden");
  const el = document.createElement("div");
  el.className = `msg ${role === "user" ? "user" : "bot"}${err ? " err" : ""}`;
  el.textContent = text;
  for (const id of files) {
    const a = document.createElement("a");
    a.className = "file";
    a.href = `/download/${encodeURIComponent(id)}`;
    a.textContent = "ดาวน์โหลดเอกสาร";
    el.append(a);
  }
  log.append(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function typing() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = '<span class="typing" aria-label="กำลังค้นหาข้อมูล"><i></i><i></i><i></i></span>';
  log.append(el);
  log.scrollTop = log.scrollHeight;
  return el;
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
      history.push({ role: "user", content: message }, { role: "assistant", content: data.text });
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
    log.querySelectorAll(".msg").forEach((m) => m.remove());
    welcome.classList.remove("hidden");
  };
  document.startViewTransition ? document.startViewTransition(reset) : reset();
  input.focus();
});

load();
// restore earlier turns after a page refresh (file buttons are not restored)
for (const t of history) add(t.role, t.content);
input.focus();
