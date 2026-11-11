// Tracking dashboard. All text goes in through textContent (h helper): AI findings and staff-typed steps are never parsed as HTML.
const app = document.getElementById("app");
const MAC = /Mac|iPhone|iPad/.test(navigator.platform);  // shortcut hints say ⌘ on Apple devices, Ctrl elsewhere
let me = null;
let users = [];

const h = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  e.append(...kids.flat().filter((x) => x != null && x !== false));
  return e;
};

// the server ends a session after 30 idle minutes (RISA_IDLE_MINUTES): the next request answers 401 and the page goes back to the login with a note
let ending = false, loginNotice = "";
function sessionEnded() {
  if (ending) return;
  ending = true; me = null; loginNotice = "หมดเวลาการใช้งาน กรุณาเข้าสู่ระบบอีกครั้ง";
  start().finally(() => { ending = false; });
}

let inflight = 0;  // requests in flight: drives the thin loading bar at the top (home.css)
const busy = (d) => document.documentElement.classList.toggle("loading", (inflight += d) > 0);
async function api(path, opts = {}) {
  busy(1);
  try {
    const r = await fetch(path.startsWith("/api/") ? path : "/api/track" + path, opts);  // a full /api/... path is used as it is (LINE lives at /api/line)
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401 && me && !path.endsWith("/login")) { sessionEnded(); throw new Error("หมดเวลาการใช้งาน"); }  // logged in a moment ago, so the session timed out
      throw new Error(typeof body.detail === "string" ? body.detail : "ผิดพลาด (" + r.status + ")");
    }
    return body;
  } finally { busy(-1); }
}
// Slow AI steps: the server reports what it is doing; the panel lists each step as it happens, with the seconds the current one has taken.
async function apiStream(path, opts, onStatus) {
  const r = await fetch("/api/track" + path, { ...opts, headers: { ...(opts.headers || {}), accept: "application/x-ndjson" } });
  if (!r.ok || !r.body) {
    const body = await r.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "ผิดพลาด (" + r.status + ")");
  }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "", out = null;
  for (;;) {
    const { value, done } = await reader.read();
    buf += dec.decode(value || new Uint8Array(), { stream: !done });
    const lines = buf.split("\n");
    buf = lines.pop();
    for (const l of done ? [...lines, buf] : lines) {
      if (!l.trim()) continue;
      const ev = JSON.parse(l);
      if (ev.status) onStatus(ev.status);
      else if (ev.error) throw new Error(ev.error);
      else if ("done" in ev) out = ev.done;
    }
    if (done) return out;
  }
}

// start(say) does the work and calls say(text) for each step. The panel replaces the card that was clicked; on failure it shows the error and a retry.
async function runProgress(from, title, start, onDone, retry) {
  const host = from.closest(".card, .doc") || from;
  const list = h("ol", { class: "prog-steps" }), t0 = { v: Date.now() };
  let cur = null, timer = null;
  const tick = () => { if (cur) cur.lastChild.textContent = " " + Math.round((Date.now() - t0.v) / 1000) + " วินาที"; };
  const say = (text) => {
    if (cur) { cur.className = "done"; cur.lastChild.remove(); }
    cur = h("li", { class: "now" }, h("span", { class: "spin" }), h("span", {}, text), h("span", { class: "muted" }, ""));
    list.append(cur); t0.v = Date.now();
  };
  say("เริ่มทำงาน");
  host.replaceChildren(h("h2", {}, title), h("p", { class: "muted sub" }, "AI กำลังทำงานอยู่ ขั้นตอนที่ทำเสร็จแล้วจะขึ้นเครื่องหมายถูก กรุณารอสักครู่"), list);
  timer = setInterval(tick, 1000);
  try {
    const out = await start(say);
    clearInterval(timer);
    await onDone(out);
  } catch (e) {
    clearInterval(timer);
    cur?.classList.replace("now", "failed");
    host.append(h("p", { class: "err" }, "ไม่สำเร็จ: " + e.message), h("div", { class: "actions" }, h("button", { class: "ghost", type: "button", onclick: retry }, "กลับ")));
  }
}
const send = (method, body) => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const form = (fields) => { const f = new FormData(); for (const [k, v] of Object.entries(fields)) f.append(k, v); return { method: "POST", body: f }; };

const STATUS = { draft: "แบบร่าง (ยังไม่ได้ส่ง)", screened: "AI ตรวจสอบแล้ว", cannot_check: "AI ตรวจสอบไม่ได้ (ยังส่งได้)", sent: "รอเจ้าหน้าที่ตรวจสอบ", approved: "อนุมัติแล้ว", returned: "ส่งกลับให้แก้ไข" };
// file formats a document may accept (set per document by staff in the step editor); none set = PDF and Word
const FORMATS = [["pdf", "PDF"], ["docx", "Word"], ["xlsx", "Excel"], ["pptx", "PowerPoint"], ["image", "รูปภาพ"]];
const DEFAULT_FMTS = ["pdf", "docx"];
const isDefaultFmts = (f) => f.length === 2 && f.includes("pdf") && f.includes("docx");
const fmtOf = (step, doc) => step?.formats?.[doc]?.length ? step.formats[doc] : DEFAULT_FMTS;
const fmtAccept = (fmts) => fmts.flatMap((f) => f === "image" ? [".jpg", ".jpeg", ".png"] : ["." + f]).join(",");
const fmtLabel = (fmts) => fmts.map((f) => FORMATS.find((x) => x[0] === f)[1]).join(" / ");
const KIND = { missing: "ขาดหายไป", incorrect: "อาจไม่ถูกต้อง", unclear: "ไม่ชัดเจน" };
const ROLE = { researcher: "นักวิจัย", staff: "เจ้าหน้าที่" };

// A navigation (another page, tab or request) cross-fades, lets rows animate in and moves focus to the page title for screen readers.
// An in-place redraw of the same page (after a save, a pin, a picked document) does none of that, so the page never flickers or steals focus.
let pageKey = null, wantFocus = false, showSeq = 0;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
function landFocus() {
  const t = wantFocus && (app.querySelector("[autofocus]") || app.querySelector("h1, h2, h3"));  // the first heading: request pages have no h1
  if (!t) return;  // a staff tab draws its title after the skeleton: staffHome calls this again then
  wantFocus = false;
  if (/^H[1-3]$/.test(t.tagName)) t.tabIndex = -1;
  t.focus({ preventScroll: true });
}
function show(...nodes) {
  const key = [me?.id, location.pathname, tab, openReq, openType].join("|"), nav = key !== pageKey;
  pageKey = key;
  const id = ++showSeq;
  const swap = () => { if (id !== showSeq) return; app.classList.toggle("nav", nav); app.replaceChildren(...nodes.flat().filter(Boolean)); if (nav) { wantFocus = true; landFocus(); } };
  // the transition callback runs a frame later, so code after show() must not expect the new nodes in the page (login uses autofocus for that)
  if (nav && app.childElementCount && document.startViewTransition && !reduceMotion.matches) document.startViewTransition(swap);
  else swap();
}
// pages about one thing (a request, a type, the profile) use the reading width, left aligned; lists and tables use the wide column (.adm)
function showRead(...nodes) { show(h("div", { class: "read" }, nodes.flat().filter(Boolean))); }
// errors show in a toast (screen readers hear it via role=alert) instead of a blocking alert(); a click dismisses it
// toast(text, undo): with an undo function it is a neutral note with an Undo button, and only that button acts on a click
const errBox = h("div", { class: "toast atoast", role: "alert", hidden: true, onclick: () => { if (!errBox.classList.contains("undo-t")) errBox.hidden = true; } });
document.body.append(errBox);
let errTimer = null;
let undoFn = null;  // the Undo of the toast on screen; Cmd/Ctrl+Z runs it too
function toast(text, undo) {
  undoFn = undo ? () => { undoFn = null; errBox.hidden = true; undo(); } : null;
  errBox.replaceChildren(h("span", {}, text), undo ? h("button", { class: "link", type: "button", onclick: undoFn }, "เลิกทำ", h("kbd", {}, MAC ? "⌘Z" : "Ctrl Z")) : null);
  errBox.classList.toggle("undo-t", !!undo);
  errBox.hidden = false; clearTimeout(errTimer); errTimer = setTimeout(() => { errBox.hidden = true; undoFn = null; }, 6000);
}
// an Undo toast and its delete wait while the pointer or focus is on it (WCAG 2.2.1: enough time), and start a fresh 6 s after
function holdToast(on) {
  if (errBox.hidden || !errBox.classList.contains("undo-t")) return;
  clearTimeout(errTimer); if (pendingDel) clearTimeout(pendingDel.timer);
  if (on) return;
  errTimer = setTimeout(() => { errBox.hidden = true; undoFn = null; }, 6000);
  if (pendingDel) pendingDel.timer = setTimeout(commitDelete, 6000);
}
errBox.addEventListener("pointerenter", () => holdToast(true));
errBox.addEventListener("pointerleave", () => holdToast(false));
errBox.addEventListener("focusin", () => holdToast(true));
errBox.addEventListener("focusout", () => holdToast(false));
function fail(e) { toast(e.message); }

// Deleting a request is optimistic: it leaves the page now and the DELETE waits 6 s so Undo can cancel it (the same pattern as files.js).
// Lists drop a request that is waiting (gone(id)); leaving the page or logging out sends the DELETE at once.
let pendingDel = null;
const gone = (id) => pendingDel?.id === id;
function deleteLater(id, text, restore) {
  commitDelete();
  pendingDel = { id, restore, timer: setTimeout(commitDelete, 6000) };
  toast(text, () => { if (pendingDel?.id !== id) return; clearTimeout(pendingDel.timer); pendingDel = null; restore(); });
}
function commitDelete() {
  if (!pendingDel) return;
  const { id, restore, timer } = pendingDel;
  clearTimeout(timer); pendingDel = null;
  return api("/submissions/" + id, { method: "DELETE" }).catch((e) => { fail(e); restore(); });
}
addEventListener("pagehide", () => {
  if (!pendingDel) return;
  fetch("/api/track/submissions/" + pendingDel.id, { method: "DELETE", keepalive: true });
  clearTimeout(pendingDel.timer); pendingDel = null;  // a page restored from the back/forward cache must not send it twice
});
// the clicked button stays disabled until its request settles, so a double click cannot send twice (two requests, two approvals)
const act = (fn) => async (ev) => {
  const b = ev?.currentTarget instanceof HTMLButtonElement ? ev.currentTarget : null;
  if (b) { b.disabled = true; b.setAttribute("aria-busy", "true"); }
  try { await fn(ev); } catch (e) { fail(e); } finally { if (b) { b.disabled = false; b.removeAttribute("aria-busy"); } }
};

// ---------- login ----------
function loginScreen() {
  const user = h("input", { type: "text", name: "username", autocomplete: "username", autocapitalize: "none", spellcheck: false, required: true, autofocus: true });
  const pass = h("input", { type: "password", name: "password", autocomplete: "current-password", required: true });
  const err = h("p", { class: "login-err", role: "alert", hidden: true });
  const submit = h("button", { class: "login-cta", type: "submit" }, "เข้าสู่ระบบ");
  const form = h("form", { class: "card login-card", onsubmit: async (ev) => {
    ev.preventDefault();
    err.hidden = true; submit.disabled = true;
    try { await api("/login", send("POST", { username: user.value.trim(), password: pass.value })); await start(); submit.disabled = false; }  // re-enabled in case loading the home page failed
    catch (e) { err.textContent = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"; err.hidden = false; pass.value = ""; pass.focus(); submit.disabled = false; }
  } },
    h("label", {}, "ชื่อผู้ใช้", user), h("label", {}, "รหัสผ่าน", pass), err, submit);
  const note = loginNotice ? h("p", { class: "login-err", role: "status" }, loginNotice) : null;
  loginNotice = "";
  show(h("div", { class: "login" }, h("h1", {}, "เข้าสู่ระบบ"), h("p", { class: "muted" }, "ระบบจำลอง ภายหลังจะเปลี่ยนเป็นบัญชีอีเมล CMU"), note, form));  // show() focuses the autofocus field
}

// ---------- shared: stepper ----------
function stepper(sub) {
  const done = (i) => sub.events.filter((e) => e.to_step > i && e.from_step <= i).map((e) => e.at.slice(0, 10)).pop();
  return h("ol", { class: "steps" }, sub.steps.map((s, i) => {
    const cls = i < sub.current_step ? "done" : i === sub.current_step ? "now" : "next";
        return h("li", { class: cls }, h("span", {}, (i + 1) + ". " + s.title), cls === "done" && done(i) ? h("span", { class: "muted" }, done(i)) : null);
  }));
}

// one finding: a small label, the field it is about, one sentence, and what to do. `lead` is an optional leading element (a checkbox).
function findingItem(f, dismissed = false, lead = null) {
  return h("div", { class: "finding " + f.kind + (dismissed ? " dismissed" : "") }, lead,
    h("span", { class: "fbody" }, h("span", { class: "fhead" }, h("span", { class: "fk" }, KIND[f.kind] || f.kind), f.field ? h("b", {}, f.field) : null),
      h("span", { class: "ft" }, f.text), f.fix ? h("span", { class: "fx" }, "แนะนำ: " + f.fix) : null));
}

// the AI's findings: a one-line count by kind, then each finding
function findings(list, dismissed = []) {
  if (!list.length) return null;
  const n = (k) => list.filter((f) => f.kind === k).length;
  const parts = ["missing", "incorrect", "unclear"].filter(n).map((k) => KIND[k] + " " + n(k));
  return h("div", { class: "findings" }, h("p", { class: "fsum" }, "AI พบ " + list.length + " ข้อสังเกต · " + parts.join(" · ")), list.map((f, i) => findingItem(f, dismissed.includes(i))));
}

// ---------- researcher ----------
function docRow(sub, name, reload) {
  const up = sub.uploads.find((u) => u.doc_name === name), def = sub.forms[name];
  const canSend = up && (up.status === "screened" || up.status === "cannot_check");
  const locked = up && (up.status === "sent" || up.status === "approved");
  const fmts = fmtOf(sub.steps[sub.current_step], name);
  const pick = h("input", { type: "file", accept: fmtAccept(fmts), hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "กำลังตรวจสอบ “" + name + "”", (say) => apiStream("/submissions/" + sub.id + "/uploads", form({ doc_name: name, file }), say), reload, reload);
  } });
  const sendBtn = canSend ? h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/uploads/" + up.id + "/send", { method: "POST" }); await reload(); }) }, "ส่งให้เจ้าหน้าที่ตรวจสอบ") : null;
  const withdraw = up && up.status === "sent" ? h("button", { class: "ghost", type: "button", onclick: act(async () => { if (confirm("ถอนเอกสารนี้กลับมาแก้ไข? เจ้าหน้าที่จะไม่เห็นในคิวตรวจสอบจนกว่าจะส่งใหม่")) { await api("/uploads/" + up.id + "/withdraw", { method: "POST" }); await reload(); } }) }, "ถอนกลับมาแก้ไข") : null;
  return h("div", { class: "doc" }, h("b", {}, def ? def.title : name), " ", up ? h("span", { class: "rv-st " + up.status }, STATUS[up.status]) : h("span", { class: "muted" }, "ยังไม่ได้ส่ง"), withdraw,
    up ? findings(up.findings) : null,
    up && up.status === "returned" ? h("p", { class: "err" }, "เจ้าหน้าที่ส่งกลับ: " + (up.note || "(ไม่มีหมายเหตุ)"))
      : up && up.note && !locked ? h("p", { class: "err" }, "หมายเหตุจากเจ้าหน้าที่ที่ส่งกลับ: " + up.note) : null,
    def ? (locked ? answersView(up) : formFill(sub, name, def, up, reload)) : null,
    def ? h("div", { class: "actions end" }, sendBtn)
      : h("div", { class: "actions" }, pick, h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, up ? "อัปโหลดใหม่" : "อัปโหลดไฟล์ (" + fmtLabel(fmts) + ")"), sendBtn));
}

// no confirm: the request leaves at once and the toast offers Undo for 6 s
const cancelRequest = (sub, after) => h("button", { class: "ghost danger", type: "button", onclick: act(async () => {
  deleteLater(sub.id, "ยกเลิกงาน “" + sub.title + "” แล้ว", () => { openReq = sub.id; researcherHome().catch(fail); });
  await after();
}) }, "ยกเลิกงานนี้");

// one request, with its form(s): opened from the home list
function subCard(sub) {
  const step = sub.steps[sub.current_step];
  const staff = users.find((u) => u.id === sub.staff_id);
  return h("section", { class: "card", id: "sub-" + sub.id },
    h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · เจ้าหน้าที่ผู้รับผิดชอบ: " + (staff ? staff.name : sub.staff_id)), stepper(sub),
    step ? h("div", {}, h("h3", {}, "เอกสารสำหรับขั้นตอนนี้"),
      step.documents.length ? step.documents.map((name) => docRow(sub, name, () => researcherHome().catch(fail))) : h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร"))
      : h("p", {}, "ดำเนินการเสร็จสิ้น"),
    sub.current_step >= sub.step_count ? null : h("div", { class: "actions end" }, cancelRequest(sub, leaveMine)));
}

// ---------- researcher home: status cards, my requests, start a new one ----------
let openReq = null, homeFilter = "";  // openReq: the request whose page is open; homeFilter: a status card that is switched on
const BUCKETS = [["action", "ต้องดำเนินการ"], ["waiting", "รอเจ้าหน้าที่ตรวจสอบ"], ["active", "กำลังดำเนินการ"], ["done", "เสร็จสิ้น"]];
const BUCKET_TAG = { action: "t-warn", waiting: "t-mut", active: "t-mut", done: "t-ok" };
// one status for a request: finished, or something to do, or waiting for staff, or simply under way
function bucketOf(sub) {
  if (sub.current_step >= sub.step_count) return { bucket: "done", item: null };
  const items = todoItems([sub]), item = items.find((i) => i.kind !== "waiting");
  return item ? { bucket: "action", item } : items.length ? { bucket: "waiting", item: items[0] } : { bucket: "active", item: null };
}
const ITEM_TEXT = (t) => t.kind === "returned" ? "ส่งกลับให้แก้ไข" : t.kind === "send" ? "พร้อมส่ง" : t.draft ? "ยังกรอกไม่ครบ" : t.kind === "waiting" ? "รอเจ้าหน้าที่ตรวจสอบ" : "ยังไม่ได้ส่ง";
const hl = (text, q) => {  // the searched words marked inside a name
  const i = q ? text.toLowerCase().indexOf(q) : -1;
  return i < 0 ? text : [text.slice(0, i), h("mark", {}, text.slice(i, i + q.length)), text.slice(i + q.length)];
};

function myRequests(subs, draw) {
  const rows = subs.map((s) => ({ s, ...bucketOf(s) })).filter((r) => !homeFilter || r.bucket === homeFilter).sort((x, y) => (x.bucket === "done") - (y.bucket === "done"));  // finished last
  return h("div", { class: "hlist" }, rows.length ? rows.map(({ s, bucket, item }) => {
    const n = Math.min(s.current_step + 1, s.step_count), pct = Math.round(100 * Math.min(s.current_step, s.step_count) / s.step_count);
    return h("div", { class: "hrow" },
      h("div", {}, h("b", {}, s.title), item ? h("span", { class: "htag " + (item.kind === "returned" ? "t-err" : BUCKET_TAG[bucket]) }, ITEM_TEXT(item)) : bucket === "done" ? h("span", { class: "htag t-ok" }, "เสร็จสิ้น") : null,
        h("small", {}, bucket === "done" ? "ดำเนินการเสร็จสิ้น" : "ขั้นที่ " + n + ": " + s.steps[s.current_step].title + (item ? " · " + item.doc + (item.kind === "returned" && item.note ? " · “" + item.note + "”" : "") : ""))),
      h("div", { class: "prog2" }, h("div", { class: "hbar" }, h("i", { style: "width:" + pct + "%" })), h("small", {}, bucket === "done" ? s.step_count + "/" + s.step_count : "ขั้นตอน " + n + "/" + s.step_count)),
      h("button", { class: bucket === "action" ? "primary" : "ghost", type: "button", onclick: () => { openReq = s.id; researcherHome().catch(fail); } },
        bucket === "action" ? (item.kind === "returned" ? "แก้ไข" : item.kind === "send" ? "ส่งเอกสาร" : "กรอกต่อ") : "ดูรายละเอียด"));
  }) : [h("p", { class: "muted pad" }, subs.length ? "ไม่มีงานในสถานะนี้" : "ยังไม่มีงานของคุณ เริ่มจาก “เริ่มงานใหม่” ด้านล่าง")]);
}

// open types, grouped by category; with many categories the groups start closed and search opens the ones with a match
function startList(posts, cats, subs) {
  const catName = new Map(cats.map((c) => [c.id, c.name]));
  const groups = [{ id: "pin", pin: true, name: "★ ปักหมุด", types: posts.filter((p) => p.pinned) }].concat(cats.map((c) => ({ id: c.id, name: c.name, types: posts.filter((p) => p.category_id === c.id) })))
    .concat([{ id: null, name: "อื่น ๆ", types: posts.filter((p) => p.category_id == null || !catName.has(p.category_id)) }]).filter((g) => g.types.length);
  const many = groups.length > 5, chips = groups.length > 6;
  let only = null;  // a chip that is switched on
  const find = h("input", { type: "search", class: "hsearch", placeholder: "ค้นหาประเภทงาน เช่น ทุน เบิก จริยธรรม", "aria-label": "ค้นหาประเภทงาน" });
  const chipBox = h("div", { class: "hchips" }), box = h("div", { class: "hlist" });
  const startOrContinue = (p) => {
    const mine = subs.find((s) => s.type_id === p.type_id);
    return mine ? h("button", { class: "ghost", type: "button", onclick: () => { openReq = mine.id; researcherHome().catch(fail); } }, "ต่องานของฉัน")
      : h("button", { class: "primary", type: "button", onclick: act(async () => { openReq = (await api("/open-types/" + p.type_id + "/start", { method: "POST" })).id; await researcherHome().catch(fail); }) }, "เริ่มส่ง");
  };
  const draw = () => {
    const q = find.value.trim().toLowerCase();
    chipBox.replaceChildren(...(chips && !q ? [h("button", { class: "hchip" + (only === null ? " on" : ""), type: "button", onclick: () => { only = null; draw(); } }, "ทั้งหมด"),
      ...groups.map((g, i) => h("button", { class: "hchip" + (only === i ? " on" : ""), type: "button", onclick: () => { only = only === i ? null : i; draw(); } }, g.name, h("small", {}, String(g.types.length))))] : []));
    const shown = groups.map((g, i) => ({ g, i, types: q ? g.types.filter((p) => p.type_name.toLowerCase().includes(q)) : g.types })).filter((x) => x.types.length && !(q && x.g.pin) && (q || only === null || only === x.i));  // search hides the pinned copy so a match never shows twice
    box.replaceChildren(...(shown.length ? shown.map(({ g, i, types }) => {
      const started = types.filter((p) => subs.some((s) => s.type_id === p.type_id)).length;
      return h("details", { class: "hg", open: q || only === i || !many || g.pin }, h("summary", {}, h("span", { class: "ch" }, "›"), h("b", {}, g.name),
        h("span", { class: "muted" }, q ? types.length + " จาก " + g.types.length : g.types.length + " ประเภท"), started ? h("span", { class: "hhit" }, "คุณเริ่มแล้ว " + started) : null),
        types.map((p) => h("div", { class: "hrow2" }, h("div", {}, h("b", {}, hl(p.type_name, q)),
          h("small", {}, p.steps.length + " ขั้นตอน · เอกสาร " + new Set(p.steps.flatMap((st) => st.documents)).size + " รายการ · ผู้รับผิดชอบ " + p.owner_name)), startOrContinue(p))));
    }) : [h("p", { class: "muted pad" }, posts.length ? "ไม่พบประเภทงานที่ตรงกัน ลองคำอื่น หรือถามแชท AI" : "ยังไม่มีงานที่เปิดรับ")]));
  };
  find.addEventListener("input", draw);
  draw();
  return h("section", {}, h("h2", { class: "sech" }, "เริ่มงานใหม่"), posts.length > 3 ? find : null, chipBox, box);
}

// back from a researcher's request page: through the history when the page pushed an entry, so Back and this button agree
function leaveMine() {
  if (history.state?.open) return history.back();
  openReq = null; researcherHome().catch(fail);
}
async function researcherHome() {
  if (openReq) {  // a request's own page: the form lives here
    const sub = gone(openReq) ? null : await api("/submissions/" + openReq).catch(() => null);
    if (sub) {
      if (history.state?.open !== openReq) history.pushState({ open: openReq }, "");  // its own history entry: browser Back and the phone back gesture return to the list
      return showRead(h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: leaveMine }, "← งานของฉัน")), subCard(sub));
    }
    openReq = null;  // cancelled or gone
    if (history.state?.open) history.replaceState({}, "");
  }
  const [list, posts, cats] = await Promise.all([api("/submissions"), api("/open-types"), api("/categories")]);
  const subs = await Promise.all(list.filter((s) => !gone(s.id)).map((s) => api("/submissions/" + s.id)));
  const info = subs.map(bucketOf), counts = Object.fromEntries(BUCKETS.map(([k]) => [k, info.filter((i) => i.bucket === k).length]));
  const resume = info.find((i) => i.bucket === "action");  // what to continue first
  const cards = h("div", { class: "hcards" }), mine = h("div");
  const draw = () => {
    cards.replaceChildren(...BUCKETS.map(([k, label]) => h("button", { class: "card2" + (k === "action" && counts.action ? " act" : "") + (homeFilter === k ? " on" : ""), type: "button", "aria-pressed": String(homeFilter === k),
      onclick: () => { homeFilter = homeFilter === k ? "" : k; draw(); } }, h("b", {}, String(counts[k])), h("span", {}, label))));
    mine.replaceChildren(myRequests(subs, draw));
  };
  draw();
  show(h("h1", { class: "page-title" }, "สวัสดี " + me.name), h("p", { class: "muted sub" }, "ภาพรวมงานของคุณ"), cards,
    h("section", {}, h("h2", { class: "sech" }, "งานของฉัน"), mine),
    resume ? h("div", { class: "hrec" }, h("span", {}, "เริ่มต่อ: ", h("b", {}, subs[info.indexOf(resume)].title), " · " + resume.item.doc + " · " + ITEM_TEXT(resume.item)),
      h("button", { class: "ghost", type: "button", onclick: () => { openReq = subs[info.indexOf(resume)].id; researcherHome().catch(fail); } }, "ไปที่งานนี้")) : null,
    startList(posts, cats, subs));
}

// ---------- staff ----------
let typeQ = "", typeCat = null;  // the type list's search text and category chip survive a redraw
let tab = "queue", openType = null, openGroup = null;  // openType: the type whose page is open in the ประเภทงาน tab
let queueAll = false;  // the review queue shows your own documents unless this is on
let filesRoot = null, filesTab = null;  // the file manager: built once, kept in the page (hidden) while another tab shows
// [key, icon, label]; null draws a divider. The Ctrl/Cmd+K palette lists the same tabs
const STAFF_TABS = [["queue", "queue", "รอตรวจสอบ"], ["subs", "list", "งานทั้งหมด"], null, ["types", "types", "ประเภทงาน"], ["files", "folder", "คลังเอกสาร"], null, ["users", "users", "ผู้ใช้"]];
let homeSeq = 0;
async function staffHome() {
  const mine = ++homeSeq;
  if (filesTab) { filesTab.close(); filesRoot.hidden = true; document.body.append(filesRoot); }
  let [queue, subs] = await Promise.all([api("/review-queue"), api("/submissions")]).catch((e) => { fail(e); return [[], []]; });
  queue = queue.filter((u) => !gone(u.submission_id)); subs = subs.filter((s) => !gone(s.id));  // a delete waiting out its Undo
  const items = STAFF_TABS.map((it) => it?.[0] === "queue" ? [...it, queue.filter((u) => u.staff_id === me.id).length] : it);
  if (mine !== homeSeq) return;  // another tab was clicked meanwhile
  const body = h("div", { class: "ws-main" });
  const menu = h("nav", { class: "ws-menu", "aria-label": "เมนู" }, items.map((it) => !it ? h("div", { class: "sep" }) : h("button", { class: "navitem", type: "button", "aria-current": it[0] === tab ? "page" : null,
    onclick: (ev) => {  // the clicked item lights up at once; the page follows when its data is in
      menu.querySelectorAll(".navitem").forEach((b) => b.removeAttribute("aria-current")); ev.currentTarget.setAttribute("aria-current", "page");
      goTab(it[0]);
    } },
    icon(it[1]), it[2], it[3] ? h("span", { class: "n" }, String(it[3])) : null)));
  // the tab draws off-page and replaces the old one when ready; the skeleton shows only if that takes longer than 150 ms,
  // so a redraw after a save keeps the old content in place instead of flashing empty
  const ws = h("div", { class: "ws" }, menu, body);
  const sk = h("div", { class: "sk-page", "aria-hidden": "true" }, h("span"), h("span"), h("span"), h("span"));
  let shown = false;
  const slow = setTimeout(() => { if (mine !== homeSeq) return; shown = true; body.append(sk); body.setAttribute("aria-busy", "true"); show(ws); }, 150);
  await ({ subs: (b) => staffSubs(b, queue), queue: (b) => staffQueue(b, queue, subs), types: staffTypes, files: staffFiles, users: staffUsers })[tab](body).catch(fail);
  clearTimeout(slow); sk.remove(); body.removeAttribute("aria-busy");
  if (mine !== homeSeq) return;
  if (!shown) show(ws);
  landFocus();
}
function goTab(k) {
  if (location.pathname !== "/") history.pushState({}, "", "/");  // from a request page: the list gets its own address back
  tab = k; openType = null; openGroup = null;
  staffHome();
}
// redraw after a change in place, keeping the scroll position (the page empties while it reloads)
async function redraw() { const y = scrollY; await staffHome(); scrollTo(0, y); }

// access list: only people staff add here can log in. Searched and paged on the server (it can hold thousands); roles change and access turns off here
async function staffUsers(body) {
  let view = "", q = "", seq = 0, timer = null, items = [], total = 0, counts = {};
  const list = h("div", { class: "ulist" }), chips = h("div", { class: "chips2", role: "group", "aria-label": "กรอง" }), more = h("button", { class: "ghost more", type: "button", hidden: true }), note = h("p", { class: "muted", role: "status" });
  const find = h("input", { type: "search", placeholder: "ค้นหาชื่อหรืออีเมล", "aria-label": "ค้นหา", autocomplete: "off", oninput: () => { clearTimeout(timer); timer = setTimeout(() => load(true), 250); } });
  const VIEWS = [["", "ทั้งหมด"], ["staff", "เจ้าหน้าที่"], ["researcher", "นักวิจัย"], ["disabled", "ปิดใช้งาน"]];
  const call = (path, method, payload) => api("/users/" + path, send(method, payload));
  const load = async (fresh) => {
    const mine = ++seq, off = fresh ? 0 : items.length;
    const r = await api("/users/page?view=" + view + "&offset=" + off + "&limit=50&q=" + encodeURIComponent(find.value.trim())).catch((e) => { fail(e); return null; });
    if (mine !== seq || !r) return;  // a newer search is already running
    items = fresh ? r.items : items.concat(r.items); total = r.total; counts = r.counts; draw();
  };
  const reload = () => load(true);
  // after a change the row stays where it is (the list is not re-sorted or re-filtered under the cursor); only the chip counts are refreshed
  const changed = async (u, patch) => { Object.assign(u, patch); draw(); const r = await api("/users/page?limit=1").catch(() => null); if (r) { counts = r.counts; draw(); } };
  const row = (u) => {
    const mineRow = u.id === me.id;
    const role = h("select", { class: "field", "aria-label": "บทบาทของ " + u.name, disabled: mineRow || !u.active, onchange: act(async () => {
      if (role.value === "staff" && !confirm("ตั้ง " + u.name + " เป็นเจ้าหน้าที่?\nเจ้าหน้าที่จะเห็นเอกสารของนักวิจัยทุกคนและตรวจอนุมัติได้")) { role.value = u.role; return; }
      try { await call(encodeURIComponent(u.id) + "/role", "PUT", { role: role.value }); toast(u.name + " เป็น" + ROLE[role.value] + "แล้ว"); } catch (e) { role.value = u.role; throw e; }
      changed(u, { role: role.value });
    }) }, Object.entries(ROLE).map(([v, t]) => h("option", { value: v, selected: v === u.role }, t)));
    const power = mineRow ? h("small", { class: "muted" }, "ของตัวเองเปลี่ยนไม่ได้")
      : h("button", { class: "ghost", type: "button", onclick: act(async () => {
        if (u.active && !confirm("ปิดใช้งาน " + u.name + "?\nเขาจะเข้าระบบไม่ได้และตัดการเชื่อม LINE ประวัติงานยังอยู่ เปิดใช้งานใหม่ได้ภายหลัง")) return;
        await call(encodeURIComponent(u.id) + "/active", "PUT", { active: !u.active }); toast(u.name + (u.active ? " ถูกปิดใช้งานแล้ว" : " เปิดใช้งานแล้ว")); changed(u, { active: !u.active });
      }) }, u.active ? "ปิดใช้งาน" : "เปิดใช้งาน");
    return h("div", { class: "urow" + (u.active ? "" : " off") },
      h("div", { class: "who" }, h("span", { class: "av" }, u.name[0].toUpperCase()), h("div", {}, h("b", {}, u.name, mineRow ? h("span", { class: "muted" }, " (คุณ)") : null, u.joined ? null : h("span", { class: "pill wait" }, "ยังไม่เคยเข้าระบบ")), h("small", { class: "muted" }, u.id))),
      h("div", { class: "uact" }, role, power));
  };
  const draw = () => {
    chips.replaceChildren(...VIEWS.map(([v, t]) => h("button", { class: "chip2", type: "button", "aria-pressed": String(v === view), onclick: () => { view = v; reload(); } }, t + " " + (counts[v] ?? ""))));
    list.replaceChildren(...(items.length ? items.map(row) : [h("p", { class: "muted" }, find.value.trim() ? "ไม่พบผู้ใช้ที่ตรงกับ “" + find.value.trim() + "”" : "ยังไม่มีผู้ใช้ในหมวดนี้")]));
    more.hidden = items.length >= total; more.textContent = "แสดงเพิ่ม (อีก " + (total - items.length) + " คน)"; more.onclick = () => load(false);
    note.textContent = items.length ? "แสดง " + items.length + " จาก " + total + " คน" : "";
  };
  // add people: type an email and press Enter (or paste a list) and each becomes a chip that says if it is correct, wrong or already there
  const addDialog = () => {
    const EMAIL = /^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/, CMU = /(^|\.)cmu\.ac\.th$/;
    let chips = [], seen = {}, seq = 0;  // seen: email -> what the server says (new, exists, disabled, invalid)
    // ok = will be added; bad = not an email or not a CMU address (it could never log in through CMU); have = already in the list
    const kind = (e) => !EMAIL.test(e) || !CMU.test(e.split("@")[1]) || seen[e] === "invalid" ? "bad" : seen[e] === "exists" || seen[e] === "disabled" ? "have" : "ok";
    const LABEL = { ok: ["✓", "ถูกต้อง"], bad: ["!", "ไม่ถูกต้อง"], have: ["•", "มีอยู่แล้ว"] };
    const why = (e) => !EMAIL.test(e) ? "ไม่ใช่รูปแบบอีเมล" : !CMU.test(e.split("@")[1]) ? "ต้องเป็นอีเมล @cmu.ac.th" : "";
    const inp = h("input", { type: "text", "aria-label": "อีเมล", placeholder: "พิมพ์อีเมลแล้วกด Enter หรือวางหลายอีเมล", autocomplete: "off", autocapitalize: "none", spellcheck: false });
    const wrap = h("div", { class: "field-chips", role: "group", "aria-label": "อีเมลที่จะเพิ่ม", onclick: () => inp.focus() });
    const note = h("p", { class: "note3", role: "status" });
    const role = h("select", { class: "field", "aria-label": "บทบาท" }, Object.entries(ROLE).map(([v, t]) => h("option", { value: v }, t)));
    const draw = () => {
      wrap.replaceChildren(...chips.map((c, i) => { const k = kind(c); return h("span", { class: "chip3 " + k, title: k === "bad" ? why(c) : "" },
        h("i", { "aria-hidden": "true" }, LABEL[k][0]), h("span", { class: "em" }, c), h("small", {}, LABEL[k][1]),
        h("button", { type: "button", "aria-label": "ลบ " + c, onclick: (e) => { e.stopPropagation(); chips.splice(i, 1); draw(); inp.focus(); } }, "✕")); }), inp);
      const n = { ok: 0, bad: 0, have: 0 }; chips.forEach((c) => n[kind(c)]++);
      go.disabled = !n.ok; go.textContent = n.ok ? "เพิ่ม " + n.ok + " คน" : "เพิ่ม";
      note.textContent = chips.length ? [n.ok && "ถูกต้อง " + n.ok, n.bad && "ไม่ถูกต้อง " + n.bad + " (ข้าม)", n.have && "มีอยู่แล้ว " + n.have + " (ข้าม)"].filter(Boolean).join(" · ") : "";
    };
    const check = async () => {
      const mine = ++seq, todo = chips.filter((c) => kind(c) !== "bad" && !(c in seen));
      if (!todo.length) return;
      const r = await call("preview", "POST", { emails: todo.join("\n") }).catch(() => null);
      if (mine !== seq || !r) return;  // a newer change is already being checked
      r.rows.forEach((x) => { seen[x.email] = x.status; }); draw();
    };
    const take = (raw) => {
      for (const t of raw.split(/[\s,;]+/).map((x) => x.trim().replace(/^["']|["']$/g, "").toLowerCase()).filter(Boolean)) if (!chips.includes(t)) chips.push(t);
      draw(); check();
    };
    const flush = () => { const t = inp.value; inp.value = ""; if (t.trim()) take(t); };
    inp.addEventListener("keydown", (e) => {
      if (["Enter", ",", " ", ";"].includes(e.key) && inp.value.trim()) { e.preventDefault(); flush(); }
      else if (e.key === "Backspace" && !inp.value && chips.length) { chips.pop(); draw(); }
    });
    inp.addEventListener("paste", (e) => { e.preventDefault(); take(e.clipboardData.getData("text")); });
    inp.addEventListener("blur", flush);
    const go = h("button", { class: "primary", type: "button", disabled: true, onclick: act(async () => {
      flush();
      const mine = chips.filter((c) => kind(c) === "ok");
      if (!mine.length) return;
      if (role.value === "staff" && !confirm("ให้ทุกคนในรายการนี้เป็นเจ้าหน้าที่?\nเจ้าหน้าที่จะเห็นเอกสารของนักวิจัยทุกคนและตรวจอนุมัติได้")) return;
      const r = await call("add", "POST", { emails: mine.join("\n"), role: role.value });
      d.close(); toast("เพิ่มแล้ว " + r.added.length + " คน"); reload();
    }) }, "เพิ่ม");
    const d = modal("เพิ่มผู้ใช้", () => d.remove(),
      h("p", { class: "muted lead" }, "เฉพาะอีเมล CMU ที่เพิ่มไว้ที่นี่เท่านั้นที่เข้าระบบได้"),
      wrap, note,
      h("div", { class: "foot" }, h("label", { class: "rolepick" }, h("span", { class: "muted" }, "บทบาท"), role), h("div", { class: "actions" }, h("button", { class: "ghost", type: "button", onclick: () => d.close() }, "ยกเลิก"), go)),
      h("p", { class: "muted hint2" }, "ชื่อจะมาจากบัญชี CMU เมื่อเขาเข้าระบบครั้งแรก"));
    draw();
    document.body.append(d); d.showModal(); inp.focus();
  };

  // who gave or took access, newest first
  const historyDialog = async () => {
    let shown = [], total = 0;
    const list = h("div", { class: "ulist" }), more = h("button", { class: "ghost more", type: "button", hidden: true });
    const WHAT = { role: (e) => "เปลี่ยนบทบาทของ " + (e.target_name || e.target) + " เป็น" + ROLE[e.detail], add: (e) => "เพิ่ม " + (e.target_name || e.target) + " เป็น" + ROLE[e.detail],
      disable: (e) => "ปิดใช้งาน " + (e.target_name || e.target), enable: (e) => "เปิดใช้งาน " + (e.target_name || e.target) };
    const draw = () => {
      list.replaceChildren(...(shown.length ? shown.map((e) => h("div", { class: "urow" }, h("div", {}, h("b", {}, (WHAT[e.action] || (() => e.action))(e)),
        h("small", { class: "muted" }, (e.actor_name || e.actor) + " · " + utc(e.at).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" })))))
        : [h("p", { class: "muted" }, "ยังไม่มีการเปลี่ยนแปลง")]));
      more.hidden = shown.length >= total; more.textContent = "แสดงเพิ่ม (อีก " + (total - shown.length) + " รายการ)";
    };
    const load = async () => { const r = await api("/users/events?limit=50&offset=" + shown.length); shown = shown.concat(r.items); total = r.total; draw(); };
    more.onclick = act(load);
    const d = modal("ประวัติการเปลี่ยนแปลงสิทธิ์", () => d.remove(), list, more);
    document.body.append(d); d.showModal();
    await load();
  };
  body.append(h("div", { class: "between" }, h("h1", { class: "page-title" }, "ผู้ใช้"), h("div", { class: "actions" }, h("button", { class: "ghost", type: "button", onclick: act(historyDialog) }, "ประวัติการเปลี่ยนแปลง"), h("button", { class: "primary", type: "button", onclick: addDialog }, "+ เพิ่มผู้ใช้"))),
    h("p", { class: "muted sub" }, "เฉพาะคนในรายการนี้เท่านั้นที่เข้าระบบได้ บทบาทมีผลในการใช้งานครั้งถัดไปของเขา"), h("section", { class: "card" }, h("div", { class: "filters" }, find), chips, list, note, more));
  await load(true);
  users = await api("/users");  // the page-wide name list stays current for the other tabs
}

async function staffFiles(body) {
  filesRoot ||= document.getElementById("files-root");
  filesTab ||= mountFiles();
  filesRoot.hidden = false;
  body.append(filesRoot);
  filesTab.open();
}

// a table of rows: cols is the CSS grid width list; head and rows are arrays of cells; a click on a row runs onclick; cells marked `.opt` hide on phones
function dtable(cols, head, rows) {
  const st = "--cols:" + cols;
  return h("div", { class: "dt", role: "table" }, h("div", { class: "trow dt head", style: st, role: "row" }, head.map((t, i) => h("span", { class: i && i < head.length - 1 ? "opt" : "", role: "columnheader" }, t))),
    ...rows.map(({ cells, onclick, label }, i) => h("div", { class: "trow dt click", style: st + ";--i:" + Math.min(i, 12), role: "row", tabindex: "0", "aria-label": label, onclick,
      onkeydown: (ev) => { if (ev.key === "Enter" && ev.target === ev.currentTarget) onclick(); } }, cells.map((c, i) => h("span", { class: i && i < cells.length - 1 ? "opt" : "", role: "cell" }, c)))));
}

async function staffSubs(body, queue = []) {
  const subs = (await api("/submissions")).filter((s) => !gone(s.id));
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const progress = (s) => {
    const done = s.current_step >= s.step_count, n = Math.min(s.current_step + 1, s.step_count);
    return h("span", { class: "prog" }, h("span", { class: "bar" }, h("i", { style: "width:" + Math.round(100 * (done ? s.step_count : s.current_step) / s.step_count) + "%" })),
      h("span", { class: "muted" }, done ? "ดำเนินการเสร็จสิ้น" : "ขั้นตอน " + n + "/" + s.step_count));
  };
  const waiting = new Set(queue.map((q) => q.submission_id));
  const find = h("input", { type: "search", placeholder: "ค้นหาชื่องาน ประเภท หรือนักวิจัย", "aria-label": "ค้นหา" });
  const status = h("select", { class: "field", "aria-label": "สถานะ" }, [["", "ทุกสถานะ"], ["active", "กำลังดำเนินการ"], ["done", "เสร็จสิ้น"]].map(([v, t]) => h("option", { value: v }, t)));
  const who = h("select", { class: "field", "aria-label": "ผู้รับผิดชอบ" }, [h("option", { value: "" }, "ผู้รับผิดชอบทุกคน"), h("option", { value: me.id }, "ของฉัน"),
    ...users.filter((u) => u.active && u.role === "staff" && u.id !== me.id).map((u) => h("option", { value: u.id }, u.name))]);
  const count = h("p", { class: "muted sub" }), list = h("div");
  const draw = () => {
    const q = find.value.trim().toLowerCase();
    const shown = subs.filter((s) => (!q || (s.title + " " + s.type_name + " " + s.researcher_ids.map(nm).join(" ")).toLowerCase().includes(q))
      && (!who.value || s.staff_id === who.value)
      && (!status.value || (status.value === "done" ? s.current_step >= s.step_count : s.current_step < s.step_count)));
    count.textContent = shown.length === subs.length ? subs.length + " รายการ" : shown.length + " จาก " + subs.length + " รายการ";
    const open = (s) => ({ label: s.title, onclick: () => staffDetail(s.id), cells: [
      h("span", {}, h("b", {}, s.researcher_ids.map(nm).join(", ")), " ", waiting.has(s.id) ? h("span", { class: "badge warn" }, "รอตรวจสอบ") : null),  // the type is the group's heading, so the researcher names the row
      nm(s.staff_id), progress(s), "›"] });
    const reqTable = (rows) => dtable("minmax(160px,1.4fr) minmax(90px,.8fr) 190px 24px", ["นักวิจัย", "ผู้รับผิดชอบ", "ความคืบหน้า", ""], rows.map(open));
    if (openGroup) {  // inside one type: every request of it
      const inGroup = shown.filter((s) => s.type_id === openGroup);
      list.replaceChildren(h("div", { class: "grpbar" }, h("button", { class: "ghost", type: "button", onclick: () => { openGroup = null; draw(); } }, "← ประเภทงานทั้งหมด"),
        h("b", {}, subs.find((s) => s.type_id === openGroup)?.type_name || "")), inGroup.length ? reqTable(inGroup) : h("p", { class: "muted" }, "ไม่พบงานที่ตรงกับตัวกรอง"));
      return;
    }
    const groups = [...new Set(shown.map((s) => s.type_id))].map((id) => {
      const mine = shown.filter((s) => s.type_id === id), wait = mine.filter((s) => waiting.has(s.id)).length;
      return { label: mine[0].type_name, onclick: () => { openGroup = id; draw(); }, cells: [h("b", {}, mine[0].type_name), String(mine.length),
        String(mine.filter((s) => s.current_step < s.step_count).length), String(mine.filter((s) => s.current_step >= s.step_count).length),
        wait ? h("span", { class: "badge warn" }, wait + " รอตรวจสอบ") : "", "›"] };
    });
    list.replaceChildren(groups.length ? dtable("minmax(160px,1.6fr) 70px 110px 90px 130px 24px", ["ประเภทงาน", "งาน", "กำลังดำเนินการ", "เสร็จสิ้น", "รอตรวจสอบ", ""], groups)
      : h("p", { class: "muted" }, subs.length ? "ไม่พบงานที่ตรงกับตัวกรอง" : "ยังไม่มีงาน นักวิจัยเริ่มเองได้จากประเภทงานที่เปิดรับงาน (เลือกได้ว่าใครเห็น ในหน้าของแต่ละประเภทงาน)"));
  };
  [find, status, who].forEach((el) => el.addEventListener(el === find ? "input" : "change", draw));
  draw();
  body.append(h("h1", { class: "page-title" }, "งานทั้งหมด"), count,
    h("section", { class: "card" }, subs.length ? h("div", { class: "filters" }, find, status, who) : null, list));
}

// one page for every request (/requests/{id}): the queue, the all-requests list and the bell all open it; picking a document or deciding redraws it in place
const requestPath = (sid) => "/requests/" + sid;
async function staffDetail(sid, pick) {
  const sub = await api("/submissions/" + sid).catch((e) => { fail(e); return null; });
  if (!sub) return;
  if (location.pathname !== requestPath(sid)) { history.pushState({ req: true }, "", requestPath(sid)); scrollTo(0, 0); }  // a new address, so refresh and the browser Back button work
  const now = new Date().toISOString(), mine = sub.staff_id === me.id, finished = sub.current_step >= sub.step_count;
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const docs = (finished ? [] : sub.steps[sub.current_step].documents).map((name) => ({ name, up: sub.uploads.find((u) => u.doc_name === name) }));
  const waiting = docs.filter((x) => x.up?.status === "sent");
  const cur = docs.find((x) => x.name === pick) || waiting[0] || docs.find((x) => x.up) || docs[0] || null, u = cur?.up, sent = u?.status === "sent";
  const again = () => staffDetail(sid, cur?.name);
  const changed = again;
  const reviewed = docs.filter((x) => x.up && (x.up.status === "approved" || x.up.status === "returned")).length;
  const rv = sent ? reviewBlock(u, mine, changed, true) : null;
  const from = sub.researcher_ids.map(nm).join(", ") || "นักวิจัย";
  const sec = (title, ...kids) => h("section", { class: "rv-sec" }, h("h3", {}, title), kids.flat());
  const manage = (title, ...kids) => { const e = sec(title, ...kids); e.classList.add("divided"); return e; };
  const viewLink = (up) => h("a", { class: "rv-open", href: "/api/track/uploads/" + up.id + "/file", target: "_blank", onclick: (ev) => ev.stopPropagation() }, "ดูเอกสาร ↗");
  const state = (x) => !x.up ? h("span", { class: "muted" }, "ยังไม่ได้ส่ง") : h("span", { class: "rv-st " + x.up.status }, x.up.status === "sent" ? "รอตรวจสอบ" : x.up.status === "approved" ? "ผ่านการตรวจสอบ" : x.up.status === "returned" ? "ส่งกลับแล้ว" : STATUS[x.up.status]);
  const pickIt = (x) => () => { if (x !== cur) staffDetail(sid, x.name); };
  const move = (to) => act(async () => { await api("/submissions/" + sid + "/move", send("POST", { to_step: to })); await changed(); });
  const owner = h("select", { class: "field", "aria-label": "ผู้รับผิดชอบงานนี้", onchange: act(async (ev) => { await api("/submissions/" + sid + "/staff", send("POST", { staff_id: ev.target.value })); await changed(); }) },
    users.filter((x) => x.active && x.role === "staff").map((x) => h("option", { value: x.id, selected: x.id === sub.staff_id }, "ผู้รับผิดชอบ " + x.name)));
  const kids = [
    sec("ข้อมูลคำขอ", h("div", { class: "rv-card" }, h("small", {}, "ประเภทงาน"), h("b", { class: "rv-type" }, sub.type_name),
      h("div", { class: "rv-meta" },
        h("div", { class: "rv-from" }, h("span", { class: "rv-av", "aria-hidden": "true" }, [...from][0].toUpperCase()), h("div", {}, h("small", {}, "นักวิจัย"), h("b", {}, from))),
        h("div", {}, h("small", {}, "ผู้รับผิดชอบ"), h("b", {}, nm(sub.staff_id))),
        h("div", {}, h("small", {}, "ขั้นตอน"), h("b", {}, finished ? "เสร็จสิ้น" : (sub.current_step + 1) + "/" + sub.step_count + " " + sub.steps[sub.current_step].title)))), stepper(sub)),
    sec(finished ? "เอกสาร" : "เอกสารของขั้นตอนนี้" + (docs.length > 1 ? " (" + docs.length + ")" : ""),
      finished ? h("p", { class: "muted" }, "ดำเนินการเสร็จสิ้น")
        : !docs.length ? h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร")
        : [docs.length > 1 ? h("div", { class: "rv-prog" }, h("span", { class: "bar" }, h("i", { style: "width:" + Math.round(100 * reviewed / docs.length) + "%" })), h("span", { class: "muted" }, "ตรวจแล้ว " + reviewed + " จาก " + docs.length)) : null,
          h("div", { class: "rv-list" }, docs.map((x) => { const can = x.up || mine; return h("div", { class: "rv-item" + (x === cur ? " on" : "") + (can ? " pick" : ""), role: can ? "button" : null, tabindex: can ? "0" : null, "aria-current": x === cur ? "true" : null,
            onclick: can ? pickIt(x) : null, onkeydown: (ev) => { if (ev.key === "Enter" && ev.target === ev.currentTarget && can) pickIt(x)(); } },
            h("span", { class: "rv-ic", "aria-hidden": "true" }, icon("form")), h("div", { class: "grow" }, h("b", {}, x.name), x.up ? h("span", { class: "muted" }, x.up.filename) : null),
            state(x), x.up && !x.up.answers.length ? viewLink(x.up) : null); }))]),
    cur ? (sent ? [u.answers.length ? sec("คำตอบ: " + cur.name, answersView(u)) : null, rv.findings.length ? sec("ข้อสังเกตจาก AI", rv.findings) : null,
        mine ? [sec("หมายเหตุถึงนักวิจัย (ไม่บังคับ)", rv.note), h("div", { class: "rv-foot" }, rv.buttons)] : h("p", { class: "muted rv-view" }, "เฉพาะผู้รับผิดชอบเท่านั้นที่ตัดสินได้")]
      : mine ? sec("เอกสาร: " + cur.name, docRow(sub, cur.name, again))  // fill in or upload for the researcher until it is sent
      : [u?.findings.length ? sec("ข้อสังเกตจาก AI", findings(u.findings, u.dismissed || [])) : null,
        h("p", { class: "muted rv-view" }, u ? STATUS[u.status] + (u.note ? " · หมายเหตุ: " + u.note : "") : "ยังไม่ได้ส่ง")]) : null,
    manage("จัดการงาน", h("div", { class: "actions" }, owner, h("span", { class: "muted" }, "เปลี่ยนผู้รับผิดชอบได้ทุกคน เมื่อคนเดิมไม่อยู่")),
      h("div", { class: "actions steps" },
        h("button", { class: "ghost", type: "button", disabled: !mine || sub.current_step <= 0, onclick: move(sub.current_step - 1) }, "ย้อนกลับหนึ่งขั้น"),
        h("button", { class: "primary", type: "button", disabled: !mine || finished, onclick: move(sub.current_step + 1) }, "ไปขั้นถัดไป"),
        mine ? h("button", { class: "ghost danger", type: "button", onclick: () => { deleteLater(sid, "ลบงาน “" + sub.title + "” แล้ว", () => staffDetail(sid).catch(fail)); leaveRequest(); } }, "ลบงานนี้")
          : h("span", { class: "muted" }, "เฉพาะเจ้าหน้าที่ผู้รับผิดชอบเท่านั้นที่แก้ไขได้"))),
    manage("ประวัติ", sub.events.length ? sub.events.map((e) => h("p", { class: "muted" }, e.at + " · ขั้น " + (e.from_step + 1) + " → " + (e.to_step + 1) + " · " + nm(e.staff_id) + (e.note ? " · " + e.note : ""))) : h("p", { class: "muted" }, "ยังไม่มีการเปลี่ยนขั้นตอน"))];
  showRead(h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: leaveRequest }, "← กลับ")), kids.flat(Infinity).filter(Boolean));  // kids nest (a branch can be a list), so flatten all the way
}

// back to the list the request was opened from (the page before it in the history, or the home list when it was opened by address)
function leaveRequest() {
  if (history.state?.req) history.back();
  else { history.replaceState({}, "", "/"); staffHome(); }
}
window.addEventListener("popstate", () => {
  if (!me) return;
  const m = location.pathname.match(/^\/requests\/(\d+)$/);
  if (m && me.role === "staff") staffDetail(Number(m[1])).catch(fail);
  else if (location.pathname === "/" && me.role === "staff") staffHome().catch(fail);
  else if (location.pathname === "/") { openReq = history.state?.open || null; researcherHome().catch(fail); }
});

// findings to dismiss, a note, approve or return: shared by the review queue and a request's page
function reviewBlock(u, mine, after, parts = false) {
  const dismissed = new Set();
  const note = h("input", { type: "text", placeholder: "หมายเหตุถึงนักวิจัย (ไม่บังคับ)" });
  const list = h("div", { class: "findings" });
  const draw = () => list.replaceChildren(...u.findings.map((f, i) => findingItem(f, dismissed.has(i),
    h("input", { type: "checkbox", checked: dismissed.has(i), "aria-label": "ปัดตก", onchange: (ev) => { ev.target.checked ? dismissed.add(i) : dismissed.delete(i); draw(); } }))));
  draw();
  const decide = (decision) => act(async () => { await api("/uploads/" + u.id + "/review", send("POST", { decision, dismissed: [...dismissed], note: note.value })); await after(); });
  const sum = u.findings.length ? h("p", { class: "fsum" }, "ข้อสังเกตจาก AI " + u.findings.length + " ข้อ · ติ๊กข้อที่ไม่ต้องสนใจเพื่อปัดตก") : null;
  const ret = h("button", { class: "ghost danger", type: "button", disabled: !mine, onclick: decide("return") }, "ส่งกลับให้แก้ไข");
  if (parts) return { findings: u.findings.length ? [sum, list] : [], note, buttons: [mine ? null : h("span", { class: "muted" }, "เฉพาะผู้รับผิดชอบเท่านั้น"), ret,
    h("button", { class: "primary", type: "button", disabled: !mine, onclick: decide("approve") }, icon("check"), "อนุมัติเอกสาร")] };  // the review window lays them out itself
  return [sum, list, note, h("div", { class: "actions" },
    h("button", { class: "primary", type: "button", disabled: !mine, onclick: decide("approve") }, "อนุมัติ"), ret,
    mine ? null : h("span", { class: "muted" }, "เฉพาะผู้รับผิดชอบเท่านั้น"))];
}

async function staffQueue(body, everyone, subs) {
  const now = new Date().toISOString();
  const stat = (n, label, kind) => h("div", { class: "stat" + (n && kind ? " " + kind : "") }, h("b", {}, String(n)), h("span", {}, label));
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const who = (sid) => (subs.find((s) => s.id === sid)?.researcher_ids || []).map(nm).join(", ");
  // the queue has one row per request (its sent documents together); the window shows every document of the step and reviews one at a time
  const ai = (n) => n ? h("span", { class: "badge warn" }, "AI พบ " + n + " ข้อ") : h("span", { class: "badge ok" }, "ไม่พบข้อสังเกต");
  const view = h("div"), filter = h("select", { class: "field", "aria-label": "แสดง", onchange: (ev) => { queueAll = ev.target.value === "all"; draw(); } },
    h("option", { value: "mine", selected: !queueAll }, "ของฉัน"), h("option", { value: "all", selected: queueAll }, "ของทุกคน"));
  const draw = () => {
    const q = queueAll ? everyone : everyone.filter((u) => u.staff_id === me.id), st = staffStats(q, queueAll ? subs : subs.filter((s) => s.staff_id === me.id), now);
    const reqs = [...new Set(q.map((u) => u.submission_id))].map((sid) => ({ sid, ups: q.filter((u) => u.submission_id === sid) }));  // q is oldest first, so is this
    const others = everyone.length - q.length;
    view.replaceChildren(...[q.length ? h("div", { class: "stats" }, stat(st.waiting, "รอตรวจสอบ", "warn"), stat(st.active, "งานที่กำลังดำเนินการ"), stat(st.old, "รอตรวจสอบเกิน 7 วัน", "err")) : null,
      q.length ? h("section", { class: "card" }, dtable("minmax(130px,1.2fr) minmax(100px,1fr) minmax(150px,1.3fr) minmax(90px,.8fr) 120px 90px 24px",
        ["งาน", "นักวิจัย", "เอกสาร", "ผู้รับผิดชอบ", "AI", "ส่งเมื่อ", ""],
        reqs.map(({ sid, ups }) => ({ label: ups[0].submission_title, onclick: () => staffDetail(sid), cells: [h("b", {}, subs.find((x) => x.id === sid)?.type_name || ups[0].submission_title), who(sid),
          ups.length === 1 ? ups[0].doc_name : ups[0].doc_name + " และอีก " + (ups.length - 1) + " ฉบับ", nm(ups[0].staff_id), ai(ups.reduce((n, u) => n + u.findings.length, 0)), agoText(ups[0].created, now), "›"] }))))
      : h("section", { class: "card empty" }, h("span", { class: "ic" }, icon("check")), h("b", {}, "ยังไม่มีเอกสารรอตรวจสอบ"),
        h("p", { class: "muted" }, others ? "ไม่มีเอกสารที่ต้องตรวจโดยคุณ · ของเจ้าหน้าที่คนอื่นมีอีก " + others + " ฉบับ (เลือก “ของทุกคน” เพื่อดู)" : "เมื่อมีนักวิจัยส่งเอกสารเพื่อตรวจสอบ รายการจะแสดงที่นี่"))].filter(Boolean));
  };
  draw();
  body.append(h("div", { class: "between head-row" }, h("div", {}, h("h1", { class: "page-title" }, "เอกสารรอตรวจสอบ"), h("p", { class: "muted sub" }, "เรียงตามวันที่ส่ง (เก่าสุดก่อน) กดแถวเพื่อตรวจสอบ")), everyone.length ? filter : null), view);
}

async function staffTypes(body) {
  const types = await api("/types");
  const open = openType && types.find((t) => t.type_id === openType);
  if (open) return typePage(body, open);
  const name = h("input", { type: "text", placeholder: "ชื่อประเภทงาน เช่น ทุน CMU Presidential, ขอเบิกค่าเดินทาง", "aria-label": "ชื่อประเภทงาน" });
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "AI กำลังร่างขั้นตอนจาก “" + file.name + "”", (say) => apiStream("/types", form({ name: name.value.trim(), file }), say), (out) => draftEditor(out.version_id), staffHome);
  } });
  const counts = Object.fromEntries(types.map((t) => [t.id, docsOf(t).length ? docsOf(t).length + " รายการ" : "ไม่มีเอกสาร"]));
  const cats = await api("/categories");
  const known = new Set(cats.map((c) => c.id)), catOf = new Map(cats.map((c) => [c.id, c.name]));
  const done = (fn) => async (...a) => { try { await fn(...a); await redraw(); } catch (e) { fail(e); } };
  const drag = {};  // the type_id being dragged onto a category chip
  // only the grip starts a drag, so text in the row stays selectable
  const row = (t) => {
    const grip = h("span", { class: "grip", title: "ลากไปวางที่หมวดด้านบนเพื่อย้าย", onmousedown: () => { r.draggable = true; }, onmouseup: () => { r.draggable = false; } });
    const pin = h("button", { class: "pin" + (t.pinned ? " on" : ""), type: "button", "aria-pressed": String(!!t.pinned), title: t.pinned ? "เลิกปักหมุด" : "ปักหมุด (แสดงก่อนใคร ๆ ทั้งฝั่งเจ้าหน้าที่และนักวิจัย)",
      onclick: () => {  // the star flips at once; a failed save flips it back
      const flip = () => { pin.classList.toggle("on"); pin.setAttribute("aria-pressed", String(pin.classList.contains("on"))); };
      flip();
      api("/types/" + t.type_id + "/pin", send("PUT", { pinned: !t.pinned })).then(redraw, (e) => { flip(); fail(e); });
    } }, "★");
    const r = h("div", { class: "trow" },
      h("span", { class: "tname" }, grip, pin, h("b", {}, t.type_name), catOf.has(t.category_id) ? h("small", { class: "tag" }, catOf.get(t.category_id)) : null),
      h("span", { class: "muted" }, t.status === "draft" ? "–" : t.steps.length),
      h("span", { class: "muted" }, counts[t.id]),
      t.status === "draft" ? h("span", { class: "badge warn" }, "ฉบับร่าง") : t.open ? h("span", { class: "badge ok", title: t.audience ? "เฉพาะ " + t.audience.map((id) => users.find((u) => u.id === id)?.name || id).join(", ") : null }, t.audience ? "เปิดรับ · " + t.audience.length + " คน" : "เปิดรับงาน") : h("span", { class: "badge" }, "ปิดรับงาน"),
      t.status === "draft" ? h("span", { class: "tools" }, h("button", { class: "ghost danger", type: "button", onclick: removeButton("ลบฉบับร่าง “" + t.type_name + "”?", "/versions/" + t.id) }, "ลบ"),
        h("button", { class: "primary", type: "button", onclick: () => draftEditor(t.id) }, "ตรวจสอบและอนุมัติ"))
        : h("button", { class: "ghost", type: "button", onclick: () => { openType = t.type_id; staffHome(); } }, "จัดการ"));
    r.addEventListener("dragstart", (ev) => { drag.type = t.type_id; ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", ""); r.classList.add("dragging"); });
    r.addEventListener("dragend", () => { r.draggable = false; r.classList.remove("dragging"); delete drag.type; });
    return r;
  };
  const head = h("div", { class: "trow head" }, h("span", {}, "ชื่อประเภท"), h("span", {}, "ขั้นตอน"), h("span", {}, "เอกสารที่ต้องส่ง"), h("span", {}, "สถานะ"), h("span"));
  const moveType = done((tid, cid) => api("/types/" + tid + "/category", send("PUT", { category_id: cid })));
  const find = h("input", { type: "search", class: "hsearch", value: typeQ, placeholder: "ค้นหาประเภทงาน", "aria-label": "ค้นหาประเภทงาน" });
  const chipBox = h("div", { class: "hchips" }), list = h("div");
  // the name of a chip turns into an input: Enter saves, Esc or leaving the box cancels
  const edit = (label, start, save, cls = "") => {
    const box = h("input", { type: "text", class: "chipin " + cls, value: start, "aria-label": "ชื่อหมวด", placeholder: "ชื่อหมวดใหม่" });
    box.addEventListener("keydown", act(async (e) => {
      if (e.key === "Escape") box.replaceWith(label);
      else if (e.key === "Enter") { if (box.value.trim() && box.value !== start) { await save(box.value); await redraw(); } else box.replaceWith(label); }
    }));
    box.addEventListener("blur", () => { if (box.isConnected) box.replaceWith(label); });
    label.replaceWith(box); box.focus(); box.select();
  };
  const chip = (key, name, n, c) => {  // c = the category (null for ทั้งหมด and อื่น ๆ); chips are also drop targets for a dragged type
    const label = h("button", { class: "hchip" + (typeCat === key ? " on" : ""), type: "button", onclick: () => { typeCat = typeCat === key && key !== null ? null : key; draw(); } }, name, h("small", {}, String(n)));
    const el = h("span", { class: "chipwrap" }, label,
      c ? h("button", { class: "lk", type: "button", title: "แก้ชื่อหมวด", "aria-label": "แก้ชื่อหมวด", onclick: () => edit(label, c.name, (v) => api("/categories/" + c.id, send("PUT", { name: v }))) }, "✎") : null,
      c && !n && !c.types ? h("button", { class: "lk danger", type: "button", title: "ลบหมวดว่าง", "aria-label": "ลบหมวดว่าง", onclick: () => { if (confirm("ลบหมวด “" + c.name + "” ?")) done(() => api("/categories/" + c.id, { method: "DELETE" }))(); } }, "✕") : null);
    if (key !== null) {
      el.addEventListener("dragover", (ev) => { if (drag.type !== undefined) { ev.preventDefault(); el.classList.add("over"); } });
      el.addEventListener("dragleave", () => el.classList.remove("over"));
      el.addEventListener("drop", (ev) => { ev.preventDefault(); el.classList.remove("over"); moveType(drag.type, key === "none" ? null : key); });
    }
    return el;
  };
  const addCat = h("button", { class: "hchip add", type: "button", onclick: () => edit(addCat, "", (v) => api("/categories", send("POST", { name: v })), "new") }, "+ หมวดหมู่ใหม่");
  const draw = () => {
    typeQ = find.value;
    const q = typeQ.trim().toLowerCase(), none = types.filter((t) => !known.has(t.category_id)).length;
    chipBox.replaceChildren(chip(null, "ทั้งหมด", types.length, null), ...cats.map((c) => chip(c.id, c.name, types.filter((t) => t.category_id === c.id).length, c)),
      ...(none && cats.length ? [chip("none", "อื่น ๆ", none, null)] : []), addCat);
    const shown = types.filter((t) => (!q || t.type_name.toLowerCase().includes(q)) && (typeCat === null || (typeCat === "none" ? !known.has(t.category_id) : t.category_id === typeCat)))
      .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
    list.replaceChildren(shown.length ? h("section", { class: "card" }, head, shown.map(row)) : h("p", { class: "muted pad" }, types.length ? "ไม่พบประเภทงานที่ตรงกัน" : "ยังไม่มีประเภทงาน กด “+ สร้างประเภทงานใหม่” เพื่อเริ่ม"));
  };
  find.addEventListener("input", draw);
  const create = modal("สร้างประเภทงานใหม่", null, h("p", { class: "muted" }, "ตั้งชื่อแล้วกรอกขั้นตอนและเอกสารเอง หรืออัปโหลดคู่มือ (ทุน เบิกจ่าย ขออนุมัติ ฯลฯ) ให้ AI ช่วยร่างให้ก็ได้ เจ้าหน้าที่ตรวจสอบและแก้ไขก่อนเปิดใช้งานเสมอ"), name,
    h("div", { class: "actions" }, pick,
      h("button", { class: "primary", type: "button", onclick: act(async () => {
        if (!name.value.trim()) { name.focus(); toast("กรุณาตั้งชื่อประเภทงาน"); return; }
        const out = await api("/types", form({ name: name.value.trim() }));
        create.close();
        await draftEditor(out.version_id);
      }) }, "สร้างและกรอกเอง"),
      h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, "อัปโหลดเอกสารให้ AI ร่างขั้นตอน (ไม่บังคับ)")));
  body.append(h("div", { class: "between head-row" }, h("div", {}, h("h1", { class: "page-title" }, "ประเภทงาน"), h("p", { class: "muted sub" }, "จัดการขั้นตอน เอกสาร แบบฟอร์ม และสถานะการเปิดรับงานได้ในที่เดียว")),
      h("button", { class: "primary", type: "button", onclick: () => create.showModal() }, "+ สร้างประเภทงานใหม่")),
    find, chipBox, list, create);
  draw();
}

// popup: x button, Esc and a click on the backdrop close it; kids go inside a .card so runProgress can take the popup over
function modal(title, onclose, ...kids) {
  const d = h("dialog", { class: "dlg", onclose, onclick: (ev) => { if (ev.target === d) d.close(); } },
    h("div", { class: "card" }, h("div", { class: "between" }, h("h2", {}, title), h("button", { class: "ghost", type: "button", "aria-label": "ปิด", onclick: () => d.close() }, "✕")), kids.flat()));
  return d;
}

// delete with a confirm; the server refuses (and says why) when requests already use it
const removeButton = (question, path, done = () => staffHome()) => act(async () => {
  if (!confirm(question)) return;
  await api(path, { method: "DELETE" });
  openType = null;
  done();
});

// one page per type: steps and documents, forms, and the post (open for researchers)
// the type's name: click it (or the pencil) to edit in place, Enter saves, Esc or leaving the box cancels
function typeTitle(t) {
  const pen = h("button", { class: "editbtn", type: "button", "aria-label": "แก้ชื่อประเภทงาน" }, "✎ แก้ชื่อ");  // always visible, so nobody has to discover that the title is editable
  const title = h("h1", { class: "page-title editable", title: "คลิกเพื่อแก้ชื่อ" }, t.type_name, pen);
  title.addEventListener("click", () => {
    const box = h("input", { type: "text", class: "titlein", value: t.type_name, "aria-label": "ชื่อประเภทงาน" });
    const edit = h("div", { class: "titleedit" }, box, h("small", { class: "muted" }, "Enter บันทึก · Esc ยกเลิก"));
    const cancel = () => { edit.replaceWith(title); pen.focus(); };
    box.addEventListener("keydown", act(async (e) => {
      if (e.key === "Escape") cancel();
      else if (e.key === "Enter") { if (box.value.trim() && box.value !== t.type_name) { await api("/types/" + t.type_id + "/name", send("PUT", { name: box.value })); staffHome(); } else cancel(); }
    }));
    box.addEventListener("blur", () => { if (edit.isConnected) edit.replaceWith(title); });
    title.replaceWith(edit); box.focus(); box.select();
  });
  return title;
}
async function typePage(body, t) {
  body.classList.add("read");
  const steps = h("section", { class: "card" }, h("div", { class: "between" }, h("h2", {}, "ขั้นตอนและเอกสาร"), h("span", { class: "tools" }, h("button", { class: "ghost", type: "button", onclick: () => draftEditor(t.id, () => { tab = "types"; staffHome(); }) }, "แก้ไข"), newVersionButton(t))),
    h("ol", { class: "steplist" }, t.steps.map((s) => h("li", {}, h("b", {}, s.title), h("span", { class: "muted block" }, s.documents.length ? "เอกสาร: " + s.documents.join(", ") : "ไม่ต้องส่งเอกสาร")))));
  const cats = await api("/categories");
  const setCat = act(async (ev) => {
    let id = ev.target.value === "" ? null : ev.target.value === "new" ? "new" : +ev.target.value;
    if (id === "new") {
      const n = prompt("ชื่อหมวดใหม่");
      if (!n || !n.trim()) { staffHome(); return; }
      id = (await api("/categories", send("POST", { name: n }))).id;
    }
    await api("/types/" + t.type_id + "/category", send("PUT", { category_id: id }));
    staffHome();
  });
  const category = h("section", { class: "card" }, h("h2", {}, "หมวดหมู่"), h("p", { class: "muted sub" }, "นักวิจัยเห็นประเภทงานนี้ในหมวดที่เลือก การเปลี่ยนหมวดไม่กระทบงานที่เริ่มไปแล้ว"),
    h("select", { class: "field", "aria-label": "หมวดหมู่", onchange: setCat }, h("option", { value: "" }, "ไม่มีหมวด (อยู่ในกลุ่ม อื่น ๆ)"),
      cats.map((c) => h("option", { value: c.id, selected: c.id === t.category_id }, c.name)), h("option", { value: "new" }, "+ สร้างหมวดใหม่…")));
  const post = h("section", { class: "card" }, h("h2", {}, "เปิดรับงาน"), h("p", { class: "muted sub" }, "เมื่อเปิดรับงาน นักวิจัยที่เห็นงานนี้กดเริ่มส่งเองได้ ผู้รับผิดชอบคือเจ้าหน้าที่ที่เลือก"), postControls(t), audienceControls(t));
  body.append(h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: () => { openType = null; staffHome(); } }, "← ประเภทงานทั้งหมด")),
    typeTitle(t), steps, category, post,
    h("section", { class: "card" }, h("h2", {}, "ลบประเภทงาน"), h("p", { class: "muted sub" }, "ลบขั้นตอน แบบฟอร์ม และทุกเวอร์ชันของประเภทงานนี้ ทำได้เมื่อยังไม่มีนักวิจัยเริ่มส่งงาน"),
      h("button", { class: "ghost danger", type: "button", onclick: removeButton("ลบประเภทงาน “" + t.type_name + "” ทั้งหมด? ย้อนกลับไม่ได้", "/types/" + t.type_id) }, "ลบประเภทงานนี้")));
}

// open a type as a post researchers can start from; the owner is staff in charge of every request started from it
function postControls(t) {
  const staff = users.filter((u) => u.active && u.role === "staff");
  const publish = (owners) => api("/types/" + t.type_id + "/publish", send("POST", owners ? { owner_ids: owners } : {}));
  const picked = new Set(t.owner_ids || []);
  const boxes = staff.map((u) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: picked.has(u.id), onchange: act(async (ev) => {
    if (ev.target.checked) picked.add(u.id); else picked.delete(u.id);
    if (!picked.size) { picked.add(u.id); ev.target.checked = true; return; }  // at least one person stays in charge
    await publish([...picked]); staffHome();
  }) }), u.name));
  return t.open
    ? h("div", { class: "owners" }, h("span", { class: "tools" }, h("span", { class: "badge ok" }, "เปิดรับงาน"),
        h("button", { class: "ghost", type: "button", onclick: act(async () => { await api("/types/" + t.type_id + "/close", { method: "POST" }); staffHome(); }) }, "ปิดรับงาน")),
      h("h3", {}, "ผู้รับผิดชอบ"), h("div", { class: "checks" }, boxes),
      h("p", { class: "muted sub" }, picked.size > 1 ? "งานใหม่ของประเภทนี้จะมอบให้คนที่มีงานค้างน้อยที่สุดในกลุ่มนี้" : "เลือกได้หลายคน งานใหม่จะมอบให้คนที่มีงานค้างน้อยที่สุด"))
    : h("button", { class: "ghost", type: "button", onclick: act(async () => { await publish(); staffHome(); }) }, "เปิดรับงาน");
}

// who sees the post: every researcher, or only the ticked ones (PUT /types/{id}/audience); each change saves at once
function audienceControls(t) {
  const chosen = new Set(t.audience || []);
  const save = (ids) => api("/types/" + t.type_id + "/audience", send("PUT", { user_ids: ids }));
  const hint = h("p", { class: "muted", hidden: true }, "ยังเห็นได้ทุกคน จนกว่าจะติ๊กอย่างน้อยหนึ่งชื่อ");
  const picks = h("div", { class: "checks", hidden: !t.audience }, users.filter((u) => u.active && u.role === "researcher").map((u) => h("label", { class: "check" },
    h("input", { type: "checkbox", checked: chosen.has(u.id), onchange: act(async (ev) => {
      ev.target.checked ? chosen.add(u.id) : chosen.delete(u.id);
      if (!chosen.size) { ev.target.checked = true; chosen.add(u.id); toast("ต้องเลือกอย่างน้อยหนึ่งคน หรือเลือก “นักวิจัยทุกคน”"); return; }
      await save([...chosen]); hint.hidden = true;
    }) }), " " + u.name)));
  const mode = (all) => h("label", { class: "check" }, h("input", { type: "radio", name: "aud" + t.type_id, checked: all === !t.audience, onchange: act(async () => {
    if (all) { await save(null); chosen.clear(); picks.querySelectorAll("input").forEach((c) => { c.checked = false; }); }
    picks.hidden = all; hint.hidden = all || chosen.size > 0;
  }) }), all ? " นักวิจัยทุกคน" : " เฉพาะคนที่เลือก");
  return h("div", { class: "audience" }, h("h3", {}, "ใครเห็นงานนี้"), h("div", { class: "checks" }, mode(true), mode(false)), picks, hint);
}

function newVersionButton(t) {
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "AI กำลังร่างขั้นตอนเวอร์ชันใหม่จาก “" + file.name + "”", (say) => apiStream("/types/" + t.type_id + "/versions", form({ file }), say), (out) => draftEditor(out.version_id), staffHome);
  } });
  return h("span", {}, pick, h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, "อัปโหลดเวอร์ชันใหม่"));
}

async function draftEditor(vid, back = staffHome) {
  const v = (await api("/types")).find((t) => t.id === vid);
  // each document is a row (name + formats pill); rows become documents and formats again on save
  let steps = v.steps.map((s) => ({ ...s, rows: s.documents.map((d) => ({ name: d, fmts: s.formats?.[d] || null })) }));
  const live = v.status === "approved", box = h("div");
  const docRow = (r, remove, add) => {
    const sum = h("summary", {}), pill = h("details", { class: "fpill" });
    const sync = () => { const f = r.fmts || DEFAULT_FMTS; sum.textContent = f.map((k) => FORMATS.find((x) => x[0] === k)[1]).join(", "); pill.classList.toggle("custom", !isDefaultFmts(f)); };
    pill.append(sum, h("div", { class: "fpop" }, FORMATS.map(([k, label]) => h("label", {}, h("input", { type: "checkbox", checked: (r.fmts || DEFAULT_FMTS).includes(k), onchange: (e) => {
      const cur = new Set(r.fmts || DEFAULT_FMTS);
      e.target.checked ? cur.add(k) : cur.delete(k);
      if (!cur.size) { e.target.checked = true; toast("ต้องเลือกอย่างน้อยหนึ่งชนิด"); return; }
      r.fmts = FORMATS.map((f) => f[0]).filter((f) => cur.has(f));
      sync();
    } }), " " + label)), h("small", {}, "ชนิดไฟล์ที่รับ")));
    sync();
    const row = h("div", { class: "docrow" }, h("input", { type: "text", value: r.name, placeholder: "ชื่อเอกสาร", "aria-label": "ชื่อเอกสาร",
      oninput: (e) => { r.name = e.target.value; }, onkeydown: (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); add(); } } }),
      pill, h("button", { class: "docdel", type: "button", "aria-label": "ลบเอกสาร", onclick: () => remove(row) }, "✕"));
    return row;
  };
  const draw = () => box.replaceChildren(...steps.map((s, i) => {
    const title = h("input", { type: "text", value: s.title, oninput: (e) => { s.title = e.target.value; } });
    const list = h("div", { class: "doclist" });
    const add = () => { const r = { name: "", fmts: null }; s.rows.push(r); const el = docRow(r, remove, add); list.append(el); el.firstChild.focus(); };
    const remove = (el) => { s.rows.splice([...list.children].indexOf(el), 1); el.remove(); };
    list.append(...s.rows.map((r) => docRow(r, remove, add)));
    return h("div", { class: "stepedit" + (s.unsure ? " unsure" : "") },
      h("div", { class: "between" }, h("span", {}, h("b", {}, "ขั้นที่ " + (i + 1)), s.unsure ? h("span", { class: "warn" }, "AI ไม่แน่ใจ ตรวจสอบก่อนอนุมัติ") : null,
        s.page && !live ? h("span", { class: "muted" }, " มาจากหน้า " + s.page + " ของเอกสาร") : null),
        h("button", { class: "lk danger", type: "button", onclick: () => { steps.splice(i, 1); draw(); } }, "ลบ")),
      h("label", {}, h("span", { class: "muted" }, "ชื่อขั้นตอน"), title),
      h("div", {}, h("span", { class: "muted" }, "เอกสารที่ต้องส่ง (ไม่มีเอกสารไม่ต้องเพิ่ม)"), list, h("button", { class: "ghost addrow2", type: "button", onclick: add }, "+ เพิ่มเอกสาร")));
  }));
  draw();
  const toStep = (s) => {  // rows -> documents + formats; blanks and repeated names are dropped, the default formats are not stored
    const { rows, formats, ...rest } = s, docs = [], fm = {};
    for (const r of rows) { const n = r.name.trim(); if (!n || docs.includes(n)) continue; docs.push(n); if (r.fmts && !isDefaultFmts(r.fmts)) fm[n] = r.fmts; }
    return { ...rest, documents: docs, ...(Object.keys(fm).length ? { formats: fm } : {}) };
  };
  const save = () => api("/versions/" + vid, send("PUT", { steps: steps.filter((s) => s.title.trim()).map(toStep) }));
  showRead(h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: back }, "← กลับ")),
    h("section", { class: "card" }, h("h2", {}, v.type_name + (live ? "" : " (ฉบับร่าง)")),
      h("p", { class: "muted" }, live ? "แก้ข้อความที่ AI เขียนผิดได้ทันที ถ้ามีนักวิจัยเริ่มส่งงานแล้ว เพิ่มหรือลบขั้นตอนไม่ได้" : "ยังไม่ใช้งานจริงจนกว่าจะกดอนุมัติ"), box,
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", onclick: () => { steps.push({ title: "", documents: [], rows: [], page: null, unsure: false }); draw(); } }, "+ เพิ่มขั้นตอน"),
        live || !v.source_file ? null : h("button", { class: "ghost", type: "button", onclick: (ev) => { if (confirm("ให้ AI ร่างใหม่? การแก้ไขที่ยังไม่บันทึกจะหายไป")) runProgress(ev.target, "AI กำลังร่างขั้นตอนใหม่", (say) => apiStream("/versions/" + vid + "/redraft", { method: "POST" }, say), () => draftEditor(vid), () => draftEditor(vid)); } }, "ให้ AI ร่างใหม่"),
        live ? h("button", { class: "primary", type: "button", onclick: act(async () => { await save(); back(); }) }, "บันทึก")
          : h("button", { class: "primary", type: "button", onclick: act(async () => { await save(); await api("/versions/" + vid + "/approve", { method: "POST" }); tab = "types"; staffHome(); }) }, "อนุมัติและเริ่มใช้งาน"))));
}

// ---------- chat drawer (researchers) ----------
// The old chat page, embedded: no chat code is copied and its history keeps working.
const removeChat = () => document.querySelectorAll("#chat-drawer, #chat-fab").forEach((e) => e.remove());
// one Escape listener for the page, not one per login: closes the notification list first, then the chat drawer
document.addEventListener("keydown", (ev) => {
  // the platform's own modifier only (Ctrl+K on a Mac is kill-line in text fields); ev.code is the physical key, so a Thai layout works too
  const mod = (MAC ? ev.metaKey && !ev.ctrlKey : ev.ctrlKey && !ev.metaKey) && !ev.altKey && !ev.shiftKey;
  if (mod && ev.code === "KeyK" && me) { ev.preventDefault(); palette(); return; }
  if (mod && ev.code === "KeyZ" && undoFn && !ev.target.closest?.("input, textarea, select, [contenteditable]")) { ev.preventDefault(); undoFn(); return; }
  if (ev.key !== "Escape" || document.querySelector("dialog[open]")) return;  // an open dialog closes itself on Esc; the drawer behind it stays
  const pill = document.querySelector(".fpill[open]");
  if (pill) { pill.open = false; pill.querySelector("summary").focus(); return; }
  const notes = document.getElementById("notes");
  if (!notes.hidden) { notes.hidden = true; document.getElementById("bell").setAttribute("aria-expanded", "false"); document.getElementById("bell").focus(); return; }
  document.querySelector("#chat-drawer:not([hidden]) .chat-head button")?.click();
});
// a click anywhere outside the notification list or an open formats pill closes it
document.addEventListener("click", (ev) => {
  document.querySelectorAll(".fpill[open]").forEach((d) => { if (!d.contains(ev.target)) d.open = false; });
  const notes = document.getElementById("notes");
  if (!notes.hidden && !ev.target.closest("#notes, #bell")) { notes.hidden = true; document.getElementById("bell").setAttribute("aria-expanded", "false"); }
});

function chatDrawer() {
  removeChat();  // two overlapping logins must not leave two drawers
  const frame = h("iframe", { class: "chat-frame", title: "ผู้ช่วย AI ของ RiSA" });
  const panel = h("aside", { class: "chat-drawer", id: "chat-drawer", hidden: true },
    h("div", { class: "chat-head" }, h("b", {}, "ถาม AI"), h("button", { class: "ghost", type: "button", "aria-label": "ปิดแชท", onclick: () => toggle(false) }, "×")), frame);
  const preload = () => { if (!frame.getAttribute("src")) frame.src = "/chat"; };  // loaded when the pointer or focus reaches the button, so it is usually ready by the click; never at page load
  const fab = h("button", { class: "primary chat-fab", id: "chat-fab", type: "button", onclick: () => toggle(true), onpointerenter: preload, onfocus: preload }, icon("chat"), "ถาม AI");
  function toggle(open) {
    panel.hidden = !open;
    fab.hidden = open;
    if (open) preload();
    (open ? panel.querySelector(".chat-head button") : fab).focus();  // keyboard users land inside the drawer, and back on the button when it closes
  }
  document.body.append(fab, panel);
}

// ---------- Ctrl/Cmd+K palette: jump to a menu, a tab or a request by typing ----------
let palSubs = [];  // the last request list: shown the moment the palette opens, then refreshed behind it (stale-while-revalidate)
function palette() {
  if (!me || document.querySelector("dialog[open]")) return;
  const away = location.pathname === "/profile";  // the profile is its own page load: leave it by address
  const home = (fn, url = "/") => () => (away ? location.assign(url) : fn());
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const items = () => [
    ...(me.role === "staff" ? STAFF_TABS.filter(Boolean).map(([k, , label]) => ({ label, tag: "เมนู", run: home(() => goTab(k)) }))
      : [{ label: "งานของฉัน", tag: "เมนู", run: home(() => { if (openReq) leaveMine(); }) },
        { label: "ถาม AI", tag: "เมนู", run: () => { const fab = document.getElementById("chat-fab"); fab ? fab.click() : location.assign("/chat"); } }]),
    { label: "โปรไฟล์ของฉัน", tag: "เมนู", run: () => location.assign("/profile") },
    ...palSubs.map((s) => ({ label: s.title, sub: me.role === "staff" ? [s.type_name, s.researcher_ids.map(nm).join(", ")].filter(Boolean).join(" · ") : s.type_name, tag: "งาน",
      run: me.role === "staff" ? home(() => staffDetail(s.id).catch(fail), requestPath(s.id)) : home(() => { openReq = s.id; researcherHome().catch(fail); }) })),
  ];
  const input = h("input", { type: "text", role: "combobox", "aria-expanded": "true", "aria-controls": "pal-list", "aria-autocomplete": "list", "aria-label": "ค้นหาเมนูหรืองาน",
    placeholder: "ไปที่… พิมพ์ชื่องาน เมนู หรือชื่อนักวิจัย", autocomplete: "off", spellcheck: false });
  const list = h("ul", { id: "pal-list", role: "listbox", "aria-label": "ผลการค้นหา" });
  const d = h("dialog", { class: "pal", "aria-label": "ค้นหาและไปที่", onclose: () => d.remove(), onclick: (ev) => { if (ev.target === d) d.close(); } }, input, list,
    h("div", { class: "pal-foot", "aria-hidden": "true" }, h("span", {}, h("kbd", {}, "↑"), " ", h("kbd", {}, "↓"), " เลือก"), h("span", {}, h("kbd", {}, "Enter"), " เปิด"), h("span", {}, h("kbd", {}, "Esc"), " ปิด")));
  let shown = [], at = 0;
  const go = (it) => { d.close(); it.run(); };
  const select = (i) => {
    at = i;
    [...list.children].forEach((li, j) => li.setAttribute("aria-selected", String(j === i)));
    input.setAttribute("aria-activedescendant", "pal-" + i);
    list.children[i]?.scrollIntoView({ block: "nearest" });
  };
  const draw = () => {
    const words = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);  // every word must appear, in any order
    shown = items().filter((it) => words.every((w) => (it.label + " " + (it.sub || "")).toLowerCase().includes(w))).slice(0, 50);
    list.replaceChildren(...(shown.length ? shown.map((it, i) => h("li", { id: "pal-" + i, role: "option", onclick: () => go(it), onpointermove: () => { if (at !== i) select(i); } },
      h("span", { class: "grow" }, h("b", {}, it.label), it.sub ? h("small", {}, it.sub) : null), h("small", { class: "tag" }, it.tag)))
      : [h("li", { class: "none", role: "presentation" }, "ไม่พบผลลัพธ์")]));
    if (shown.length) select(Math.min(at, shown.length - 1)); else input.removeAttribute("aria-activedescendant");
  };
  input.addEventListener("input", () => { at = 0; draw(); });
  input.addEventListener("keydown", (ev) => {
    if (ev.isComposing) return;  // Thai and other IMEs use the arrows and Enter while composing
    if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && shown.length) { ev.preventDefault(); select((at + (ev.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length); }
    else if (ev.key === "Enter" && shown[at]) { ev.preventDefault(); go(shown[at]); }
  });
  document.body.append(d); d.showModal(); draw();
  api("/submissions").then((r) => { palSubs = r.filter((s) => !gone(s.id)); if (d.open) draw(); }, () => {});
}

// ---------- notifications: what changed on my requests; the page checks once a minute ----------
let bellTimer = null;
// a notification is one sentence naming its request in (brackets) or “quotes”; pull the request out so the headline stays short
// the kind sets the colour, the same words as the badges elsewhere: warn = waits for you, ok = done, err = sent back, info = the rest
const noteKind = (t) => /ส่งกลับ/.test(t) ? ["err", "undo"] : /อนุมัติแล้ว|เสร็จสิ้น/.test(t) ? ["ok", "check"] : /รอตรวจสอบ|ได้รับมอบหมาย/.test(t) ? ["warn", "clock"] : ["info", "info"];
function noteParts(text) {
  const a = text.match(/^(.*?) \((.+)\)(?:: (.*))?$/);
  if (a) return { head: a[1], where: a[2], note: a[3] || "" };
  const b = text.match(/^(.*?)“(.+)”(.*)$/);
  if (b) return { head: b[3].trim() || b[1].trim(), where: b[2], note: "" };
  return { head: text, where: "", note: "" };
}

function mountBell() {
  clearInterval(bellTimer);
  const bell = document.getElementById("bell"), n = document.getElementById("bellN"), panel = document.getElementById("notes");
  bell.hidden = !me; panel.hidden = true;
  if (!me) return;
  const count = (k) => { n.hidden = !k; n.textContent = String(k); document.title = (k ? "(" + k + ") " : "") + "RiSA"; };
  const refresh = () => api("/notifications").then((r) => count(r.unread)).catch(() => {});
  const go = (sid) => { panel.hidden = true; bell.setAttribute("aria-expanded", "false"); if (me.role === "staff") staffDetail(sid).catch(fail); else { openReq = sid; researcherHome().catch(fail); } };
  const close = () => { panel.hidden = true; bell.setAttribute("aria-expanded", "false"); };
  bell.setAttribute("aria-expanded", "false");
  bell.onclick = act(async () => {
    if (!panel.hidden) { close(); return; }
    const r = await api("/notifications"), now = new Date().toISOString();
    panel.replaceChildren(h("div", { class: "nh" }, "การแจ้งเตือน"), ...(r.items.length ? r.items.map((it) => { const t = noteParts(it.text), [kind, ic] = noteKind(it.text);
      return h("button", { type: "button", class: (it.seen ? "" : "new ") + "k-" + kind, onclick: () => go(it.submission_id) }, h("span", { class: "dot", "aria-hidden": "true" }, icon(ic)),
        h("span", { class: "nb" }, h("span", { class: "nt" }, t.head), t.where ? h("span", { class: "nc" }, t.where) : null, t.note ? h("span", { class: "nn" }, t.note) : null), h("time", {}, agoText(it.created, now))); })
      : [h("p", {}, "ยังไม่มีการแจ้งเตือน")]));
    panel.hidden = false; bell.setAttribute("aria-expanded", "true");
    if (r.unread) { await api("/notifications/seen", { method: "POST" }); count(0); }  // read once the list is open
  });
  refresh();
  bellTimer = setInterval(refresh, 60000);
}

// ---------- profile: /profile shows the person's own details, LINE link and logout ----------
let avatarV = Date.now();  // changes when the photo changes, so the browser fetches it again
const avatar = (p) => p.photo ? h("img", { class: "av", src: "/api/track/profile/avatar?v=" + avatarV, alt: "" })
  : h("span", { class: "av", style: p.avatar_color ? "background:" + p.avatar_color + ";color:#fff" : null }, p.name[0].toUpperCase());
const AVATAR_COLORS = ["#0f766e", "#2563eb", "#7c3aed", "#be123c", "#b45309", "#475569"];  // same list as the server

function renderWho() {
  document.getElementById("who").replaceChildren(...(me ? [avatar(me), h("span", {}, me.name, h("small", {}, ROLE[me.role]))] : []));
}

// the photo is cropped square and shrunk to 256 px in the browser, so uploads stay small whatever the camera made
async function squarePhoto(file) {
  const bmp = await createImageBitmap(file).catch(() => { throw new Error("ใช้ได้เฉพาะรูป JPG, PNG หรือ WebP"); });
  const s = Math.min(bmp.width, bmp.height), c = document.createElement("canvas");
  c.width = c.height = 256;
  c.getContext("2d").drawImage(bmp, (bmp.width - s) / 2, (bmp.height - s) / 2, s, s, 0, 0, 256, 256);
  return new Promise((ok, no) => c.toBlob((b) => b ? ok(b) : no(new Error("อ่านรูปไม่ได้")), "image/jpeg", 0.85));
}

// a researcher links their LINE account by typing a one-time code into the LINE chat
async function lineCard() {
  const st = await api("/api/line/status").catch(() => null);
  if (!st?.enabled) return null;
  const card = h("section", { class: "card" });
  const draw = (linked) => card.replaceChildren(h("h2", {}, "LINE"),
    h("p", { class: "muted sub" }, linked ? "เชื่อมบัญชี LINE แล้ว ✓ ถามคำถามและรับแจ้งเตือนผ่าน LINE ได้" : "เชื่อมบัญชี LINE เพื่อถามคำถามและรับแจ้งเตือนผ่าน LINE"),
    h("div", { class: "actions" }, linked
      ? h("button", { class: "ghost", type: "button", onclick: act(async () => { await api("/api/line/unlink", { method: "POST" }); draw(false); }) }, "ยกเลิกการเชื่อม")
      : h("button", { class: "primary", type: "button", onclick: act(async () => {
        const c = await api("/api/line/code", { method: "POST" });
        const d = modal("เชื่อมบัญชี LINE", async () => { d.remove(); draw((await api("/api/line/status").catch(() => st)).linked); },
          h("p", {}, "1. เพิ่มเพื่อน LINE ของ RiSA" + (st.bot_id ? " (" + st.bot_id + ")" : "")), h("p", {}, "2. พิมพ์รหัสนี้ส่งในแชทนั้น:"),
          h("p", { class: "linecode" }, c.code), h("p", { class: "muted" }, "รหัสใช้ได้ " + c.minutes + " นาที ใช้ได้ครั้งเดียว · ยกเลิกการเชื่อมได้โดยพิมพ์ “ยกเลิกการเชื่อมต่อ” ใน LINE"));
        document.body.append(d); d.showModal();
      }) }, "เชื่อม LINE")));
  draw(st.linked);
  return card;
}

async function profileScreen() {
  const p = await api("/profile");
  let color = p.avatar_color;
  const preview = h("div", { class: "avbig" });
  const drawAvatar = () => preview.replaceChildren(avatar({ ...p, avatar_color: color }));
  const mark = () => [...swatches.children].forEach((b, i) => b.setAttribute("aria-pressed", String(AVATAR_COLORS[i] === (color || AVATAR_COLORS[0]))));
  const swatches = h("div", { class: "swatches", role: "group", "aria-label": "สีโปรไฟล์" }, AVATAR_COLORS.map((c) => h("button", {
    type: "button", class: "swatch", style: "background:" + c, "aria-label": c, onclick: () => { color = c; drawAvatar(); mark(); } })));
  mark();
  drawAvatar();
  const pick = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", hidden: true, onchange: act(async () => {
    const f = pick.files[0]; pick.value = "";
    if (!f) return;
    await api("/profile/avatar", { method: "PUT", body: form({ file: await squarePhoto(f) }).body });
    avatarV = Date.now(); me.photo = true; profileScreen().catch(fail);
  }) });
  const field = (label, input, hint) => h("label", { class: "pfield" }, h("span", {}, label), input, hint ? h("small", { class: "muted" }, hint) : null);
  const name = h("input", { type: "text", maxlength: 80, required: true, value: p.name, autocomplete: "name" });
  const phone = h("input", { type: "tel", maxlength: 20, value: p.phone, autocomplete: "tel", inputmode: "tel" });
  const faculty = h("input", { type: "text", maxlength: 100, value: p.faculty, autocomplete: "organization" });
  const saved = h("span", { class: "muted", role: "status" });
  const save = h("button", { class: "primary", type: "submit" }, "บันทึก");
  const logout = h("button", { class: "ghost", type: "button", onclick: doLogout }, "ออกจากระบบ");
  const info = h("form", { class: "card profile", onsubmit: act(async (ev) => {
    ev.preventDefault(); saved.textContent = "";
    const r = await api("/profile", send("PUT", { name: name.value, phone: phone.value, faculty: faculty.value, avatar_color: color }));
    me = { ...me, name: r.name, avatar_color: r.avatar_color }; renderWho(); saved.textContent = "บันทึกแล้ว ✓";
  }) },
    h("div", { class: "avhead" }, preview, h("div", { class: "avside" }, swatches, h("div", { class: "actions" },
      h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, p.photo ? "เปลี่ยนรูป" : "อัปโหลดรูป"),
      p.photo ? h("button", { class: "ghost", type: "button", onclick: act(async () => { await api("/profile/avatar", { method: "DELETE" }); avatarV = Date.now(); me.photo = false; profileScreen().catch(fail); }) }, "ลบรูป") : null, pick))),
    field("ชื่อที่แสดง", name), field("เบอร์โทร", phone, "เจ้าหน้าที่ใช้ติดต่อเมื่อเอกสารต้องแก้ไข"), field("คณะ / หน่วยงาน", faculty),
    h("div", { class: "pfield" }, h("span", {}, "อีเมล / รหัสผู้ใช้"), h("b", {}, p.id), h("small", { class: "muted" }, "บทบาท: " + ROLE[p.role] + " · แก้ไขเองไม่ได้ ติดต่อเจ้าหน้าที่หากไม่ถูกต้อง")),
    h("div", { class: "actions" }, save, saved));
  showRead(h("div", { class: "formbar" }, h("a", { class: "ghost", href: "/" }, "← กลับ")), h("h1", { class: "page-title" }, "โปรไฟล์ของฉัน"), info,
    p.role === "researcher" ? await lineCard() : null, h("div", { class: "actions" }, logout));
}

const doLogout = async () => { await commitDelete(); await api("/logout", { method: "POST" }); if (location.pathname !== "/") location.assign("/"); else start(); };

// ---------- start ----------
async function boot() {
  removeChat();
  openReq = history.state?.open || null; homeFilter = "";  // a new login starts on the overview; a refresh on a request page stays on it
  try { me = await api("/me"); } catch { me = null; }
  const logout = document.getElementById("logout");
  renderWho();
  logout.hidden = !me;
  document.getElementById("chatlink").hidden = !me || me.role !== "researcher";  // staff do not use the chat
  logout.onclick = doLogout;
  palSubs = [];  // the palette must not show the previous person's requests
  const find = document.getElementById("find");
  find.hidden = !me; find.onclick = palette;
  find.setAttribute("aria-keyshortcuts", MAC ? "Meta+K" : "Control+K");
  document.getElementById("findKey").textContent = MAC ? "⌘K" : "Ctrl K";
  if (!me) { tab = "queue"; mountBell(); return loginScreen(); }  // the next staff member starts on the inbox
  if (location.pathname === "/profile") return profileScreen();  // no bell here: a notification opens a request, which lives on the home page
  mountBell();
  users = await api("/users");
  const req = location.pathname.match(/^\/requests\/(\d+)$/);
  if (req && me.role === "staff") return staffDetail(Number(req[1]));  // opened by address (refresh or a shared link)
  if (req) history.replaceState({}, "", "/");  // researchers have their own request view on the home page
  await (me.role === "staff" ? staffHome : researcherHome)();
  if (me.role === "researcher") chatDrawer();
}

// any failed load shows an alert instead of leaving a blank page
function start() { return boot().catch(fail); }
start();
