// Tracking dashboard. All text goes in through textContent (h helper): AI findings and staff-typed steps are never parsed as HTML.
const app = document.getElementById("app");
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

async function api(path, opts = {}) {
  const r = await fetch("/api/track" + path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "ผิดพลาด (" + r.status + ")");
  return body;
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
const KIND = { missing: "ขาดหายไป", incorrect: "อาจไม่ถูกต้อง", unclear: "ไม่ชัดเจน" };
const ROLE = { researcher: "นักวิจัย", staff: "เจ้าหน้าที่" };

function show(...nodes) { app.replaceChildren(...nodes.flat().filter(Boolean)); }
function fail(e) { alert(e.message); }
const act = (fn) => async (ev) => { try { await fn(ev); } catch (e) { fail(e); } };

// ---------- login ----------
function loginScreen() {
  const user = h("input", { type: "text", name: "username", autocomplete: "username", autocapitalize: "none", spellcheck: false, required: true });
  const pass = h("input", { type: "password", name: "password", autocomplete: "current-password", required: true });
  const err = h("p", { class: "login-err", role: "alert", hidden: true });
  const submit = h("button", { class: "login-cta", type: "submit" }, "เข้าสู่ระบบ");
  const form = h("form", { class: "card login-card", onsubmit: async (ev) => {
    ev.preventDefault();
    err.hidden = true; submit.disabled = true;
    try { await api("/login", send("POST", { username: user.value.trim(), password: pass.value })); start(); }
    catch (e) { err.textContent = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"; err.hidden = false; pass.value = ""; pass.focus(); submit.disabled = false; }
  } },
    h("label", {}, "ชื่อผู้ใช้", user), h("label", {}, "รหัสผ่าน", pass), err, submit);
  show(h("div", { class: "login" }, h("h1", {}, "เข้าสู่ระบบ"), h("p", { class: "muted" }, "ระบบจำลอง ภายหลังจะเปลี่ยนเป็นบัญชีอีเมล CMU"), form));
  user.focus();
}

// ---------- shared: stepper ----------
function stepper(sub) {
  const done = (i) => sub.events.filter((e) => e.to_step > i && e.from_step <= i).map((e) => e.at.slice(0, 10)).pop();
  return h("ol", { class: "steps" }, sub.steps.map((s, i) => {
    const cls = i < sub.current_step ? "done" : i === sub.current_step ? "now" : "next";
        return h("li", { class: cls }, h("span", {}, (i + 1) + ". " + s.title), cls === "done" && done(i) ? h("span", { class: "muted" }, done(i)) : null);
  }));
}

function findings(list, dismissed = []) {
  return list.map((f, i) => h("div", { class: "finding " + f.kind + (dismissed.includes(i) ? " dismissed" : "") }, h("b", {}, KIND[f.kind] || f.kind), " · ", f.text));
}

// ---------- researcher ----------
function docRow(sub, name, reload) {
  const up = sub.uploads.find((u) => u.doc_name === name), def = sub.forms[name];
  const canSend = up && (up.status === "screened" || up.status === "cannot_check");
  const locked = up && (up.status === "sent" || up.status === "approved");
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "กำลังตรวจสอบ “" + name + "”", (say) => apiStream("/submissions/" + sub.id + "/uploads", form({ doc_name: name, file }), say), reload, reload);
  } });
  const sendBtn = canSend ? h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/uploads/" + up.id + "/send", { method: "POST" }); reload(); }) }, "ส่งให้เจ้าหน้าที่ตรวจสอบ") : null;
  const withdraw = up && up.status === "sent" ? h("button", { class: "ghost", type: "button", onclick: act(async () => { if (confirm("ถอนเอกสารนี้กลับมาแก้ไข? เจ้าหน้าที่จะไม่เห็นในคิวตรวจสอบจนกว่าจะส่งใหม่")) { await api("/uploads/" + up.id + "/withdraw", { method: "POST" }); reload(); } }) }, "ถอนกลับมาแก้ไข") : null;
  return h("div", { class: "doc" }, h("b", {}, def ? def.title : name), " ", up ? h("span", { class: "muted" }, STATUS[up.status]) : h("span", { class: "muted" }, "ยังไม่ได้ส่ง"), withdraw,
    up ? findings(up.findings) : null,
    up && up.status === "returned" ? h("p", { class: "err" }, "เจ้าหน้าที่ส่งกลับ: " + (up.note || "(ไม่มีหมายเหตุ)"))
      : up && up.note && !locked ? h("p", { class: "err" }, "หมายเหตุจากเจ้าหน้าที่ที่ส่งกลับ: " + up.note) : null,
    def ? (locked ? answersView(up) : formFill(sub, name, def, up, reload)) : null,
    def ? h("div", { class: "actions end" }, sendBtn)
      : h("div", { class: "actions" }, pick, h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, up ? "อัปโหลดใหม่" : "อัปโหลดไฟล์ (.pdf / .docx)"), sendBtn));
}

const cancelRequest = (sub, after) => h("button", { class: "ghost danger", type: "button", onclick: act(async () => {
  if (!confirm("ยกเลิกงาน “" + sub.title + "” ? ข้อมูลที่กรอกไว้จะถูกลบ")) return;
  await api("/submissions/" + sub.id, { method: "DELETE" });
  after();
}) }, "ยกเลิกงานนี้");

function subCard(sub) {
  const step = sub.steps[sub.current_step];
  const staff = users.find((u) => u.id === sub.staff_id);
  return h("section", { class: "card", id: "sub-" + sub.id },
    h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · เจ้าหน้าที่ผู้รับผิดชอบ: " + (staff ? staff.name : sub.staff_id)), stepper(sub),
    step ? h("div", {}, h("h3", {}, "เอกสารสำหรับขั้นตอนนี้"),
      step.documents.length ? step.documents.map((name) => docRow(sub, name, () => researcherHome().catch(fail))) : h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร"))
      : h("p", {}, "ดำเนินการเสร็จสิ้น"),
    sub.current_step >= sub.step_count ? null : h("div", { class: "actions end" }, cancelRequest(sub, () => researcherHome().catch(fail))));
}

function openPosts(posts, subs) {
  if (!posts.length) return null;
  return h("section", { class: "card" }, h("h2", {}, "งานที่เปิดรับ"), h("p", { class: "muted" }, "เลือกงานที่ต้องการส่ง ระบบจะสร้างงานของคุณเอง"),
    posts.map((p) => h("div", { class: "list-row" },
      h("span", {}, h("b", {}, p.type_name), " ", h("span", { class: "muted" }, p.steps.length + " ขั้นตอน · เอกสาร: " + ([...new Set(p.steps.flatMap((s) => s.documents))].join(", ") || "ไม่มี") + " · ผู้รับผิดชอบ " + p.owner_name)),
      (() => {
        const mine = subs.find((s) => s.type_id === p.type_id), go = (id) => { const el = document.getElementById("sub-" + id); el?.closest("details")?.setAttribute("open", ""); el?.scrollIntoView({ behavior: "smooth" }); };
        return mine ? h("button", { class: "ghost", type: "button", onclick: () => go(mine.id) }, "ไปที่งานของฉัน")
          : h("button", { class: "primary", type: "button", onclick: act(async () => { const out = await api("/open-types/" + p.type_id + "/start", { method: "POST" }); await researcherHome(); go(out.id); }) }, "เริ่มส่ง");
      })())));
}

async function researcherHome() {
  const [list, posts] = await Promise.all([api("/submissions"), api("/open-types")]);
  const subs = await Promise.all(list.map((s) => api("/submissions/" + s.id)));
  const todo = todoItems(subs);
  show(
    h("section", { class: "card" }, h("h2", {}, "สิ่งที่ต้องทำ"),
      todo.length ? todo.map((t) => h("div", { class: "todo " + t.kind },
        h("span", {}, h("b", {}, t.sub.title), " · ", t.doc, " ",
          t.kind === "returned" ? h("span", { class: "err" }, "ส่งกลับให้แก้ไข: " + (t.note || "(ไม่มีหมายเหตุ)"))
            : h("span", { class: "muted" }, { send: "ตรวจสอบแล้ว พร้อมส่งให้เจ้าหน้าที่", fill: t.draft ? "แบบร่าง ยังกรอกไม่ครบ" : "ยังไม่ได้ส่ง ต้องกรอกหรืออัปโหลด", waiting: "รอเจ้าหน้าที่ตรวจสอบ" }[t.kind])),
        h("button", { class: "ghost", type: "button", onclick: () => document.getElementById("sub-" + t.sub.id).scrollIntoView({ behavior: "smooth" }) }, "ไปที่งานนี้")))
        : h("p", { class: "muted" }, "ไม่มีงานค้าง")),
    openPosts(posts, subs),
    ...(subs.some((s) => s.current_step < s.step_count) ? subs.filter((s) => s.current_step < s.step_count).map(subCard) : []),
    subs.some((s) => s.current_step >= s.step_count) ? h("details", { class: "card done-sub" }, h("summary", {}, "งานที่เสร็จสิ้น (" + subs.filter((s) => s.current_step >= s.step_count).length + ")"), subs.filter((s) => s.current_step >= s.step_count).map(subCard)) : null,
    subs.length ? null : h("section", { class: "card" }, h("p", { class: "muted" }, posts.length ? "ยังไม่มีงานของคุณ เริ่มจาก “งานที่เปิดรับ” ด้านบน" : "ยังไม่มีงาน และยังไม่มีงานที่เปิดรับ")));
}

// ---------- staff ----------
let tab = "queue", openType = null, openGroup = null;  // openType: the type whose page is open in the ประเภทงาน tab
let filesRoot = null, filesTab = null;  // the file manager: built once, kept in the page (hidden) while another tab shows
async function staffHome() {
  if (filesTab) { filesTab.close(); filesRoot.hidden = true; document.body.append(filesRoot); }
  const [queue, subs] = await Promise.all([api("/review-queue"), api("/submissions")]).catch((e) => { fail(e); return [[], []]; });
  const items = [["queue", "queue", "รอตรวจสอบ", queue.length], ["subs", "list", "งานทั้งหมด"], null, ["types", "types", "ประเภทงาน"], ["files", "folder", "คลังเอกสาร"]];
  const body = h("div", { class: "ws-main" });
  const menu = h("nav", { class: "ws-menu" }, items.map((it) => !it ? h("div", { class: "sep" }) : h("button", { class: "navitem", type: "button", "aria-current": String(it[0] === tab), onclick: () => { tab = it[0]; openType = null; openGroup = null; staffHome(); } },
    icon(it[1]), it[2], it[3] ? h("span", { class: "n" }, String(it[3])) : null)));
  show(h("div", { class: "ws" }, menu, body));
  ({ subs: (b) => staffSubs(b, queue), queue: (b) => staffQueue(b, queue, subs), types: staffTypes, files: staffFiles })[tab](body).catch(fail);
}

async function staffFiles(body) {
  filesRoot ||= document.getElementById("files-root");
  filesTab ||= mountFiles();
  filesRoot.hidden = false;
  body.append(filesRoot);
  filesTab.open();
}

async function staffSubs(body, queue = []) {
  const [subs, types] = await Promise.all([api("/submissions"), api("/types")]);
  const approved = types.filter((t) => t.status === "approved");
  const title = h("input", { type: "text", placeholder: "เช่น ขอเบิกค่าเดินทาง - นิดา" });
  const type = h("select", { class: "field" }, approved.map((t) => h("option", { value: t.id }, t.type_name + " (v" + t.version + ")")));
  const researchers = users.filter((u) => u.role === "researcher").map((u) => h("label", { class: "check" }, h("input", { type: "checkbox", value: u.id }), " " + u.name));
  const staffSel = h("select", { class: "field" }, users.filter((u) => u.role === "staff").map((u) => h("option", { value: u.id, selected: u.id === me.id }, u.name)));
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const lab = (text, el) => h("label", { class: "lbl" }, h("span", {}, text), el);
  const progress = (s) => {
    const done = s.current_step >= s.step_count, n = Math.min(s.current_step + 1, s.step_count);
    return h("span", { class: "prog" }, h("span", { class: "bar" }, h("i", { style: "width:" + Math.round(100 * (done ? s.step_count : s.current_step) / s.step_count) + "%" })),
      h("span", { class: "muted" }, done ? "ดำเนินการเสร็จสิ้น" : "ขั้นตอน " + n + "/" + s.step_count));
  };
  const waiting = new Set(queue.map((q) => q.submission_id));
  const find = h("input", { type: "search", placeholder: "ค้นหาชื่องาน ประเภท หรือนักวิจัย", "aria-label": "ค้นหา" });
  const status = h("select", { class: "field", "aria-label": "สถานะ" }, [["", "ทุกสถานะ"], ["review", "รอตรวจสอบ"], ["active", "กำลังดำเนินการ"], ["done", "เสร็จสิ้น"]].map(([v, t]) => h("option", { value: v }, t)));
  const who = h("select", { class: "field", "aria-label": "ผู้รับผิดชอบ" }, [h("option", { value: "" }, "ผู้รับผิดชอบทุกคน"), h("option", { value: me.id }, "ของฉัน"),
    ...users.filter((u) => u.role === "staff" && u.id !== me.id).map((u) => h("option", { value: u.id }, u.name))]);
  const count = h("p", { class: "muted sub" }), list = h("div");
  const draw = () => {
    const q = find.value.trim().toLowerCase();
    const shown = subs.filter((s) => (!q || (s.title + " " + s.type_name + " " + s.researcher_ids.map(nm).join(" ")).toLowerCase().includes(q))
      && (!who.value || s.staff_id === who.value)
      && (!status.value || (status.value === "review" ? waiting.has(s.id) : status.value === "done" ? s.current_step >= s.step_count : s.current_step < s.step_count)));
    count.textContent = shown.length === subs.length ? subs.length + " รายการ" : shown.length + " จาก " + subs.length + " รายการ";
    const row = (s) => h("div", { class: "list-row" },
      h("span", { class: "grow" }, h("b", {}, s.title), " ", waiting.has(s.id) ? h("span", { class: "badge warn" }, "รอตรวจสอบ") : null,
        h("span", { class: "muted block" }, "นักวิจัย " + s.researcher_ids.map(nm).join(", ") + " · ผู้รับผิดชอบ " + nm(s.staff_id))),
      progress(s),
      h("button", { class: "ghost", type: "button", onclick: () => staffDetail(s.id) }, "ดูรายละเอียด"));
    if (openGroup) {  // inside one type: every request of it
      const inGroup = shown.filter((s) => s.type_id === openGroup);
      list.replaceChildren(h("div", { class: "grpbar" }, h("button", { class: "ghost", type: "button", onclick: () => { openGroup = null; draw(); } }, "← ประเภทงานทั้งหมด"),
        h("b", {}, subs.find((s) => s.type_id === openGroup)?.type_name || "")), ...(inGroup.length ? inGroup.map(row) : [h("p", { class: "muted" }, "ไม่พบงานที่ตรงกับตัวกรอง")]));
      return;
    }
    const groups = [...new Set(shown.map((s) => s.type_id))].map((id) => {
      const mine = shown.filter((s) => s.type_id === id);
      return h("div", { class: "list-row" },
        h("span", { class: "grow" }, h("b", {}, mine[0].type_name), " ", mine.some((s) => waiting.has(s.id)) ? h("span", { class: "badge warn" }, mine.filter((s) => waiting.has(s.id)).length + " รอตรวจสอบ") : null,
          h("span", { class: "muted block" }, mine.length + " งาน · กำลังดำเนินการ " + mine.filter((s) => s.current_step < s.step_count).length + " · เสร็จสิ้น " + mine.filter((s) => s.current_step >= s.step_count).length)),
        h("button", { class: "ghost", type: "button", onclick: () => { openGroup = id; draw(); } }, "เปิดดูงาน"));
    });
    list.replaceChildren(...(groups.length ? groups : [h("p", { class: "muted" }, subs.length ? "ไม่พบงานที่ตรงกับตัวกรอง" : "ยังไม่มีงาน นักวิจัยเริ่มเองได้จากงานที่เปิดรับงาน หรือสร้างให้ด้านล่าง")]));
  };
  [find, status, who].forEach((el) => el.addEventListener(el === find ? "input" : "change", draw));
  draw();
  body.append(h("h1", { class: "page-title" }, "งานทั้งหมด"), count,
    h("section", { class: "card" }, subs.length ? h("div", { class: "filters" }, find, status, who) : null, list),
    h("section", { class: "card" }, h("h2", {}, "สร้างงานใหม่ให้นักวิจัย"), h("p", { class: "muted sub" }, "สร้างงานในนามนักวิจัยที่เลือก"),
      approved.length ? h("div", { class: "newform" },
        lab("ชื่องาน", title), lab("ประเภทงาน", type), lab("ผู้รับผิดชอบ", staffSel),
        h("div", { class: "lbl wide" }, h("span", {}, "เลือกนักวิจัย"), h("div", { class: "checks" }, researchers)),
        h("div", { class: "wide actions end" }, h("button", { class: "primary", type: "button", onclick: act(async () => {
          const ids = [...body.querySelectorAll(".checks input:checked")].map((c) => c.value);
          await api("/submissions", send("POST", { title: title.value.trim(), version_id: +type.value, researcher_ids: ids, staff_id: staffSel.value }));
          staffHome();
        }) }, "สร้างงาน"))) : h("p", { class: "muted" }, "ต้องมีประเภทงานที่อนุมัติแล้วก่อน (เมนู ประเภทงาน)")));
}

// one document of a request, as staff see it: the researcher's view for the in-charge staff (who may fill it in), plus review once sent
function staffDoc(sub, name, mine) {
  const up = sub.uploads.find((u) => u.doc_name === name), again = () => staffDetail(sub.id).catch(fail);
  if (!mine) return h("div", { class: "doc" }, h("b", {}, name), " ", h("span", { class: "muted" }, up ? STATUS[up.status] : "ยังไม่ได้ส่ง"), up ? (up.answers.length ? answersView(up) : h("a", { href: "/api/track/uploads/" + up.id + "/file", target: "_blank" }, "เปิดไฟล์ " + up.filename)) : null);
  if (up && up.status === "sent") return h("div", { class: "doc" }, h("b", {}, name), " ", h("span", { class: "muted" }, STATUS.sent),
    up.answers.length ? answersView(up) : h("a", { href: "/api/track/uploads/" + up.id + "/file", target: "_blank" }, "เปิดไฟล์ " + up.filename), ...reviewBlock(up, true, again));
  return docRow(sub, name, again);
}

async function staffDetail(sid) {
  const sub = await api("/submissions/" + sid);
  const mine = sub.staff_id === me.id;
  const nm = (id) => users.find((u) => u.id === id)?.name || id;
  const move = (to) => act(async () => { await api("/submissions/" + sid + "/move", send("POST", { to_step: to })); staffDetail(sid); });
  const owner = h("select", { class: "field", "aria-label": "ผู้รับผิดชอบงานนี้", onchange: act(async (ev) => { await api("/submissions/" + sid + "/staff", send("POST", { staff_id: ev.target.value })); staffDetail(sid); }) },
    users.filter((u) => u.role === "staff").map((u) => h("option", { value: u.id, selected: u.id === sub.staff_id }, "ผู้รับผิดชอบ " + u.name)));
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · นักวิจัย " + sub.researcher_ids.map(nm).join(", ")), h("div", { class: "actions" }, owner, h("span", { class: "muted" }, "เปลี่ยนผู้รับผิดชอบได้ทุกคน เมื่อคนเดิมไม่อยู่")), stepper(sub),
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", disabled: !mine || sub.current_step <= 0, onclick: move(sub.current_step - 1) }, "ย้อนกลับหนึ่งขั้น"),
        h("button", { class: "primary", type: "button", disabled: !mine || sub.current_step >= sub.step_count, onclick: move(sub.current_step + 1) }, "ไปขั้นถัดไป"),
        mine ? h("button", { class: "ghost danger", type: "button", onclick: act(async () => { if (confirm("ลบงาน “" + sub.title + "” ทั้งหมด? ย้อนกลับไม่ได้")) { await api("/submissions/" + sid, { method: "DELETE" }); staffHome(); } }) }, "ลบงานนี้")
          : h("span", { class: "muted" }, "เฉพาะเจ้าหน้าที่ผู้รับผิดชอบเท่านั้นที่แก้ไขได้"))),
    h("section", { class: "card" }, h("h2", {}, "เอกสารของขั้นตอนนี้"),
      mine ? h("p", { class: "muted sub" }, "กรอกหรืออัปโหลดแทนนักวิจัยได้จนกว่าจะส่ง เมื่อส่งแล้วตรวจสอบและอนุมัติได้ที่นี่") : h("p", { class: "muted sub" }, "ดูได้อย่างเดียว"),
      sub.current_step >= sub.step_count ? h("p", { class: "muted" }, "ดำเนินการเสร็จสิ้น")
        : !sub.steps[sub.current_step].documents.length ? h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร")
        : sub.steps[sub.current_step].documents.map((d) => staffDoc(sub, d, mine))),
    h("section", { class: "card" }, h("h2", {}, "ประวัติ"), sub.events.length ? sub.events.map((e) => h("p", { class: "muted" }, e.at + " · ขั้น " + (e.from_step + 1) + " → " + (e.to_step + 1) + " · " + nm(e.staff_id) + (e.note ? " · " + e.note : ""))) : h("p", { class: "muted" }, "ยังไม่มีการเปลี่ยนขั้นตอน")));
}

// findings to dismiss, a note, approve or return: shared by the review queue and a request's page
function reviewBlock(u, mine, after) {
  const dismissed = new Set();
  const note = h("input", { type: "text", placeholder: "หมายเหตุถึงนักวิจัย (ไม่บังคับ)" });
  const list = h("div");
  const draw = () => list.replaceChildren(...u.findings.map((f, i) => h("label", { class: "finding " + f.kind + (dismissed.has(i) ? " dismissed" : ""), style: "display:block" },
    h("input", { type: "checkbox", checked: dismissed.has(i), onchange: (ev) => { ev.target.checked ? dismissed.add(i) : dismissed.delete(i); draw(); } }), " ", h("b", {}, KIND[f.kind]), " · ", f.text, " ", h("span", { class: "muted" }, "(ติ๊ก = ปัดตก)"))));
  draw();
  const decide = (decision) => act(async () => { await api("/uploads/" + u.id + "/review", send("POST", { decision, dismissed: [...dismissed], note: note.value })); after(); });
  return [list, note, h("div", { class: "actions" },
    h("button", { class: "primary", type: "button", disabled: !mine, onclick: decide("approve") }, "อนุมัติ"),
    h("button", { class: "ghost danger", type: "button", disabled: !mine, onclick: decide("return") }, "ส่งกลับให้แก้ไข"),
    mine ? null : h("span", { class: "muted" }, "เฉพาะผู้รับผิดชอบเท่านั้น"))];
}

async function staffQueue(body, q, subs) {
  const now = new Date().toISOString(), st = staffStats(q, subs, now);
  const stat = (n, label) => h("div", { class: "stat" }, h("b", {}, String(n)), h("span", {}, label));
  body.append(...[h("h1", { class: "page-title" }, "เอกสารรอตรวจสอบ"), h("p", { class: "muted sub" }, "เรียงตามวันที่ส่ง (เก่าสุดก่อน)"),
    q.length ? h("div", { class: "stats" }, stat(st.waiting, "รอตรวจสอบ"), stat(st.active, "งานที่กำลังดำเนินการ"), stat(st.old, "รอตรวจสอบเกิน 7 วัน")) : null,
    q.length ? h("div", {}, q.map((u) => {
    const rv = reviewBlock(u, u.staff_id === me.id, staffHome);
    const ai = u.findings.length ? h("span", { class: "badge warn" }, "AI พบ " + u.findings.length + " ข้อ") : h("span", { class: "badge ok" }, "AI ไม่พบข้อสังเกต (หรือตรวจสอบไม่ได้)");
    return h("div", { class: "doc" }, h("div", { class: "between" }, h("span", {}, h("b", {}, u.doc_name), " ", h("span", { class: "muted" }, "· " + u.submission_title)), ai),
      h("p", { class: "muted sub" }, "ผู้รับผิดชอบ " + (users.find((x) => x.id === u.staff_id)?.name || u.staff_id) + " · ส่ง " + agoText(u.created, now)), " ",
      u.answers.length ? answersView(u) : h("a", { href: "/api/track/uploads/" + u.id + "/file", target: "_blank" }, "เปิดไฟล์ " + u.filename),
      ...rv);
  })) : h("section", { class: "card empty" }, h("span", { class: "ic" }, icon("check")), h("b", {}, "ยังไม่มีเอกสารรอตรวจสอบ"), h("p", { class: "muted" }, "เมื่อมีนักวิจัยส่งเอกสารเพื่อตรวจสอบ รายการจะแสดงที่นี่"))].filter(Boolean));
}

async function staffTypes(body) {
  const types = await api("/types");
  const open = openType && types.find((t) => t.type_id === openType);
  if (open) return typePage(body, open);
  const name = h("input", { type: "text", placeholder: "ชื่อประเภทงาน (เว้นว่างไว้ให้ AI ตั้งชื่อจากเอกสาร) เช่น ทุน CMU Presidential, ขอเบิกค่าเดินทาง" });
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "AI กำลังร่างขั้นตอนจาก “" + file.name + "”", (say) => apiStream("/types", form({ name: name.value.trim(), file }), say), (out) => draftEditor(out.version_id), staffHome);
  } });
  const counts = Object.fromEntries(await Promise.all(types.filter((t) => t.status === "approved").map(async (t) => {
    const by = await formsByDoc(t), docs = docsOf(t);
    return [t.id, docs.length ? "แบบฟอร์มพร้อมใช้งาน " + docs.filter((d) => by[d]?.status === "approved").length + "/" + docs.length : "ไม่มีเอกสาร"];
  })));
  body.append(h("h1", { class: "page-title" }, "ประเภทงาน"), h("p", { class: "muted sub" }, "จัดการขั้นตอน เอกสาร แบบฟอร์ม และสถานะการเปิดรับงานได้ในที่เดียว"),
    h("section", { class: "card" }, types.length ? types.map((t) => h("div", { class: "list-row" },
      h("span", { class: "grow" }, h("b", {}, t.type_name), " ", h("span", { class: "muted" }, "v" + t.version),
        h("span", { class: "muted block" }, t.status === "draft" ? "ฉบับร่าง (ยังไม่ใช้งาน)" : t.steps.length + " ขั้นตอน · " + counts[t.id])),
      t.status === "approved" && t.open ? h("span", { class: "badge ok" }, "เปิดรับงาน") : null,
      t.status === "draft" ? h("span", { class: "tools" }, h("button", { class: "ghost danger", type: "button", onclick: removeButton("ลบฉบับร่าง “" + t.type_name + "”?", "/versions/" + t.id) }, "ลบ"),
        h("button", { class: "primary", type: "button", onclick: () => draftEditor(t.id) }, "ตรวจสอบและอนุมัติ"))
        : h("button", { class: "ghost", type: "button", onclick: () => { openType = t.type_id; staffHome(); } }, "จัดการ")))
      : h("p", { class: "muted" }, "ยังไม่มีประเภทงาน อัปโหลดคู่มือด้านล่างเพื่อเริ่ม")),
    h("section", { class: "card" }, h("h2", {}, "สร้างประเภทงานใหม่"), h("p", { class: "muted" }, "อัปโหลดคู่มือหรือประกาศของงานนั้น (ทุน เบิกจ่าย ขออนุมัติ ฯลฯ) แล้ว AI ช่วยร่างขั้นตอนและเอกสารที่ต้องส่ง เจ้าหน้าที่ตรวจสอบและแก้ไขก่อนเปิดใช้งาน"), name,
      h("div", { class: "actions" }, pick, h("button", { class: "primary", type: "button", onclick: () => pick.click() }, "อัปโหลดเอกสารเพื่อให้ AI ร่างขั้นตอน"))));
}

// delete with a confirm; the server refuses (and says why) when requests already use it
const removeButton = (question, path, done = () => staffHome()) => act(async () => {
  if (!confirm(question)) return;
  await api(path, { method: "DELETE" });
  openType = null;
  done();
});

// one page per type: steps and documents, forms, and the post (open for researchers)
async function typePage(body, t) {
  const steps = h("section", { class: "card" }, h("div", { class: "between" }, h("h2", {}, "ขั้นตอนและเอกสาร"), newVersionButton(t)),
    h("ol", { class: "steplist" }, t.steps.map((s) => h("li", {}, h("b", {}, s.title), h("span", { class: "muted block" }, s.documents.length ? "เอกสาร: " + s.documents.join(", ") : "ไม่ต้องส่งเอกสาร")))));
  const post = h("section", { class: "card" }, h("h2", {}, "เปิดรับงาน"), h("p", { class: "muted sub" }, "เมื่อเปิดรับงาน นักวิจัยทุกคนเห็นงานนี้และกดเริ่มส่งเองได้ ผู้รับผิดชอบคือเจ้าหน้าที่ที่เลือก"), postControls(t));
  body.append(h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: () => { openType = null; staffHome(); } }, "← ประเภทงานทั้งหมด")),
    h("h1", { class: "page-title" }, t.type_name), h("p", { class: "muted sub" }, "v" + t.version + " · ใช้งานอยู่"), steps, await formsSection(t), post,
    h("section", { class: "card" }, h("h2", {}, "ลบประเภทงาน"), h("p", { class: "muted sub" }, "ลบขั้นตอน แบบฟอร์ม และทุกเวอร์ชันของประเภทงานนี้ ทำได้เมื่อยังไม่มีนักวิจัยเริ่มส่งงาน"),
      h("button", { class: "ghost danger", type: "button", onclick: removeButton("ลบประเภทงาน “" + t.type_name + "” ทั้งหมด? ย้อนกลับไม่ได้", "/types/" + t.type_id) }, "ลบประเภทงานนี้")));
}

// open a type as a post researchers can start from; the owner is staff in charge of every request started from it
function postControls(t) {
  const staff = users.filter((u) => u.role === "staff");
  const publish = (owner) => api("/types/" + t.type_id + "/publish", send("POST", owner ? { owner_id: owner } : {}));
  const owner = h("select", { class: "field", "aria-label": "ผู้รับผิดชอบงานนี้", onchange: act(async (ev) => { await publish(ev.target.value); staffHome(); }) },
    staff.map((u) => h("option", { value: u.id, selected: u.id === t.owner_id }, "ผู้รับผิดชอบ " + u.name)));
  return t.open
    ? h("span", { class: "tools" }, h("span", { class: "badge ok" }, "เปิดรับงาน"), owner, h("button", { class: "ghost", type: "button", onclick: act(async () => { await api("/types/" + t.type_id + "/close", { method: "POST" }); staffHome(); }) }, "ปิดรับงาน"))
    : h("button", { class: "ghost", type: "button", onclick: act(async () => { await publish(); staffHome(); }) }, "เปิดรับงาน");
}

function newVersionButton(t) {
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    runProgress(ev.target, "AI กำลังร่างขั้นตอนเวอร์ชันใหม่จาก “" + file.name + "”", (say) => apiStream("/types/" + t.type_id + "/versions", form({ file }), say), (out) => draftEditor(out.version_id), staffHome);
  } });
  return h("span", {}, pick, h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, "อัปโหลดเวอร์ชันใหม่"));
}

async function draftEditor(vid) {
  const v = (await api("/types")).find((t) => t.id === vid);
  let steps = v.steps.map((s) => ({ ...s }));
  const box = h("div");
  const draw = () => box.replaceChildren(...steps.map((s, i) => {
    const title = h("input", { type: "text", value: s.title, oninput: (e) => { s.title = e.target.value; } });
    const docs = h("textarea", { rows: 2, placeholder: "เอกสารที่ต้องเตรียม (บรรทัดละหนึ่งรายการ)", oninput: (e) => { s.documents = e.target.value.split("\n").map((x) => x.trim()).filter(Boolean); } }, s.documents.join("\n"));
    return h("div", { class: "stepedit" + (s.unsure ? " unsure" : "") },
      h("b", {}, "ขั้นที่ " + (i + 1)), s.unsure ? h("span", { class: "warn" }, "AI ไม่แน่ใจ ตรวจสอบก่อนอนุมัติ") : null,
      s.page ? h("span", { class: "muted" }, "มาจากหน้า " + s.page + " ของเอกสาร") : null, title, docs,
      h("button", { class: "ghost danger", type: "button", onclick: () => { steps.splice(i, 1); draw(); } }, "ลบขั้นตอนนี้"));
  }));
  draw();
  const save = () => api("/versions/" + vid, send("PUT", { steps: steps.filter((s) => s.title.trim()) }));
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, v.type_name + " v" + v.version + " (ฉบับร่าง)"),
      h("p", { class: "muted" }, "ยังไม่ใช้งานจริงจนกว่าจะกดอนุมัติ"), box,
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", onclick: () => { steps.push({ title: "", documents: [], page: null, unsure: false }); draw(); } }, "+ เพิ่มขั้นตอน"),
        h("button", { class: "ghost", type: "button", onclick: (ev) => { if (confirm("ให้ AI ร่างใหม่? การแก้ไขที่ยังไม่บันทึกจะหายไป")) runProgress(ev.target, "AI กำลังร่างขั้นตอนใหม่", (say) => apiStream("/versions/" + vid + "/redraft", { method: "POST" }, say), () => draftEditor(vid), () => draftEditor(vid)); } }, "ให้ AI ร่างใหม่"),
        h("button", { class: "primary", type: "button", onclick: act(async () => { await save(); await api("/versions/" + vid + "/approve", { method: "POST" }); tab = "types"; staffHome(); }) }, "อนุมัติและเริ่มใช้งาน"))));
}

// ---------- chat drawer (researchers) ----------
// The old chat page, embedded: no chat code is copied and its history keeps working.
const removeChat = () => document.querySelectorAll("#chat-drawer, #chat-fab").forEach((e) => e.remove());
// one Escape listener for the page, not one per login
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") document.querySelector("#chat-drawer:not([hidden]) .chat-head button")?.click(); });

function chatDrawer() {
  removeChat();  // two overlapping logins must not leave two drawers
  const frame = h("iframe", { class: "chat-frame", title: "ผู้ช่วย AI ของ RiSA" });
  const panel = h("aside", { class: "chat-drawer", id: "chat-drawer", hidden: true },
    h("div", { class: "chat-head" }, h("b", {}, "ถาม AI"), h("button", { class: "ghost", type: "button", "aria-label": "ปิดแชท", onclick: () => toggle(false) }, "×")), frame);
  const fab = h("button", { class: "primary chat-fab", id: "chat-fab", type: "button", onclick: () => toggle(true) }, icon("chat"), "ถาม AI");
  function toggle(open) {
    panel.hidden = !open;
    fab.hidden = open;
    if (open && !frame.getAttribute("src")) frame.src = "/chat";  // loaded on first open, not at page load
  }
  document.body.append(fab, panel);
}

// ---------- notifications: what changed on my requests; the page checks once a minute ----------
let bellTimer = null;
function mountBell() {
  clearInterval(bellTimer);
  const bell = document.getElementById("bell"), n = document.getElementById("bellN"), panel = document.getElementById("notes");
  bell.hidden = !me; panel.hidden = true;
  if (!me) return;
  const count = (k) => { n.hidden = !k; n.textContent = String(k); document.title = (k ? "(" + k + ") " : "") + "RiSA"; };
  const refresh = () => api("/notifications").then((r) => count(r.unread)).catch(() => {});
  const go = (sid) => { panel.hidden = true; if (me.role === "staff") staffDetail(sid).catch(fail); else researcherHome().then(() => document.getElementById("sub-" + sid)?.scrollIntoView({ behavior: "smooth" })).catch(fail); };
  bell.onclick = act(async () => {
    if (!panel.hidden) { panel.hidden = true; return; }
    const r = await api("/notifications"), now = new Date().toISOString();
    panel.replaceChildren(...(r.items.length ? r.items.map((it) => h("button", { type: "button", class: it.seen ? "" : "new", onclick: () => go(it.submission_id) }, it.text, h("small", {}, agoText(it.created, now))))
      : [h("p", {}, "ยังไม่มีการแจ้งเตือน")]));
    panel.hidden = false;
    if (r.unread) { await api("/notifications/seen", { method: "POST" }); count(0); }  // read once the list is open
  });
  refresh();
  bellTimer = setInterval(refresh, 60000);
}

// ---------- start ----------
async function boot() {
  removeChat();
  try { me = await api("/me"); } catch { me = null; }
  const logout = document.getElementById("logout");
  document.getElementById("who").replaceChildren(...(me ? [h("span", { class: "av" }, me.name[0].toUpperCase()), h("span", {}, me.name, h("small", {}, ROLE[me.role]))] : []));
  logout.hidden = !me;
  document.getElementById("chatlink").hidden = !me || me.role !== "researcher";  // staff do not use the chat
  mountBell();
  logout.onclick = async () => { await api("/logout", { method: "POST" }); start(); };
  if (!me) { tab = "queue"; return loginScreen(); }  // the next staff member starts on the inbox
  users = await api("/mock-users");
  await (me.role === "staff" ? staffHome : researcherHome)();
  if (me.role === "researcher") chatDrawer();
}

// any failed load shows an alert instead of leaving a blank page
function start() { return boot().catch(fail); }
start();
