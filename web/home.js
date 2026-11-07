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
const send = (method, body) => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const form = (fields) => { const f = new FormData(); for (const [k, v] of Object.entries(fields)) f.append(k, v); return { method: "POST", body: f }; };

const STATUS = { screened: "AI ตรวจแล้ว", cannot_check: "AI ตรวจไม่ได้ (ยังส่งได้)", sent: "รอเจ้าหน้าที่ตรวจ", approved: "อนุมัติแล้ว", returned: "ส่งกลับให้แก้ไข" };
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
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: act(async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    await api("/submissions/" + sub.id + "/uploads", form({ doc_name: name, file }));
    reload();
  }) });
  const sendBtn = canSend ? h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/uploads/" + up.id + "/send", { method: "POST" }); reload(); }) }, "ส่งให้เจ้าหน้าที่ตรวจ") : null;
  return h("div", { class: "doc" }, h("b", {}, def ? def.title : name), " ", up ? h("span", { class: "muted" }, STATUS[up.status]) : h("span", { class: "muted" }, "ยังไม่ได้ส่ง"),
    up ? findings(up.findings) : null,
    up && up.status === "returned" ? h("p", { class: "err" }, "เจ้าหน้าที่ส่งกลับ: " + (up.note || "(ไม่มีหมายเหตุ)")) : null,
    def ? (locked ? answersView(up) : formFill(sub, name, def, up, reload)) : null,
    def ? h("div", { class: "actions end" }, sendBtn)
      : h("div", { class: "actions" }, pick, h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, up ? "อัปโหลดใหม่" : "อัปโหลดไฟล์ (.pdf / .docx)"), sendBtn));
}

function subCard(sub) {
  const step = sub.steps[sub.current_step];
  const staff = users.find((u) => u.id === sub.staff_id);
  return h("section", { class: "card", id: "sub-" + sub.id },
    h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · เจ้าหน้าที่ผู้ดูแล: " + (staff ? staff.name : sub.staff_id)), stepper(sub),
    step ? h("div", {}, h("h3", {}, "เอกสารสำหรับขั้นตอนนี้"),
      step.documents.length ? step.documents.map((name) => docRow(sub, name, () => researcherHome().catch(fail))) : h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร"))
      : h("p", {}, "งานนี้เสร็จสิ้นแล้ว"));
}

function openPosts(posts, subs) {
  if (!posts.length) return null;
  return h("section", { class: "card" }, h("h2", {}, "งานที่เปิดรับ"), h("p", { class: "muted" }, "เลือกงานที่ต้องการส่ง ระบบจะสร้างงานของคุณเอง"),
    posts.map((p) => h("div", { class: "list-row" },
      h("span", {}, h("b", {}, p.type_name), " ", h("span", { class: "muted" }, p.steps.length + " ขั้นตอน · เอกสาร: " + ([...new Set(p.steps.flatMap((s) => s.documents))].join(", ") || "ไม่มี") + " · ผู้ดูแล " + p.owner_name)),
      (() => {
        const mine = subs.find((s) => s.type_id === p.type_id), go = (id) => document.getElementById("sub-" + id)?.scrollIntoView({ behavior: "smooth" });
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
          t.kind === "returned" ? h("span", { class: "err" }, "ส่งกลับให้แก้ไข: " + (t.note || "(ไม่มีหมายเหตุ)")) : h("span", { class: "muted" }, "รอเจ้าหน้าที่ตรวจ")),
        h("button", { class: "ghost", type: "button", onclick: () => document.getElementById("sub-" + t.sub.id).scrollIntoView({ behavior: "smooth" }) }, "ไปที่งานนี้")))
        : h("p", { class: "muted" }, "ไม่มีงานค้าง")),
    openPosts(posts, subs),
    subs.length ? subs.map(subCard) : h("section", { class: "card" }, h("p", { class: "muted" }, posts.length ? "ยังไม่มีงานของคุณ เริ่มจาก “งานที่เปิดรับ” ด้านบน" : "ยังไม่มีงาน และยังไม่มีงานที่เปิดรับ")));
}

// ---------- staff ----------
let tab = "queue";
let filesRoot = null, filesTab = null;  // the file manager: built once, kept in the page (hidden) while another tab shows
async function staffHome() {
  if (filesTab) { filesTab.close(); filesRoot.hidden = true; document.body.append(filesRoot); }
  const [queue, subs] = await Promise.all([api("/review-queue"), api("/submissions")]).catch((e) => { fail(e); return [[], []]; });
  const items = [["queue", "queue", "รอตรวจ", queue.length], ["subs", "list", "ทุกงาน"], null, ["types", "types", "ประเภทงาน"], ["forms", "form", "แบบฟอร์ม"], ["files", "folder", "เอกสารสำหรับแชท"]];
  const body = h("div", { class: "ws-main" });
  const menu = h("nav", { class: "ws-menu" }, items.map((it) => !it ? h("div", { class: "sep" }) : h("button", { class: "navitem", type: "button", "aria-current": String(it[0] === tab), onclick: () => { tab = it[0]; staffHome(); } },
    icon(it[1]), it[2], it[3] ? h("span", { class: "n" }, String(it[3])) : null)));
  show(h("div", { class: "ws" }, menu, body));
  ({ subs: staffSubs, queue: (b) => staffQueue(b, queue, subs), types: staffTypes, forms: staffForms, files: staffFiles })[tab](body).catch(fail);
}

async function staffFiles(body) {
  filesRoot ||= document.getElementById("files-root");
  filesTab ||= mountFiles();
  filesRoot.hidden = false;
  body.append(filesRoot);
  filesTab.open();
}

async function staffSubs(body) {
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
      h("span", { class: "muted" }, done ? "เสร็จสิ้น" : "ขั้น " + n + "/" + s.step_count));
  };
  body.append(h("h1", { class: "page-title" }, "ทุกงาน"), h("p", { class: "muted sub" }, subs.length + " งาน"),
    h("section", { class: "card" },
      subs.length ? subs.map((s) => h("div", { class: "list-row" },
        h("span", { class: "grow" }, h("b", {}, s.title), h("span", { class: "muted block" }, s.type_name + " · นักวิจัย " + s.researcher_ids.map(nm).join(", ") + " · ผู้ดูแล " + nm(s.staff_id))),
        progress(s),
        h("button", { class: "ghost", type: "button", onclick: () => staffDetail(s.id) }, "เปิด")))
        : h("p", { class: "muted" }, "ยังไม่มีงาน นักวิจัยเริ่มเองได้จากงานที่เปิดรับ หรือสร้างให้ด้านล่าง")),
    h("section", { class: "card" }, h("h2", {}, "สร้างงานให้นักวิจัย"), h("p", { class: "muted sub" }, "ใช้เมื่อต้องการสร้างงานแทนนักวิจัยที่ระบุชื่อ"),
      approved.length ? h("div", { class: "newform" },
        lab("ชื่องาน", title), lab("ประเภทงาน", type), lab("ผู้ดูแล", staffSel),
        h("div", { class: "lbl wide" }, h("span", {}, "นักวิจัย"), h("div", { class: "checks" }, researchers)),
        h("div", { class: "wide actions end" }, h("button", { class: "primary", type: "button", onclick: act(async () => {
          const ids = [...body.querySelectorAll(".checks input:checked")].map((c) => c.value);
          await api("/submissions", send("POST", { title: title.value.trim(), version_id: +type.value, researcher_ids: ids, staff_id: staffSel.value }));
          staffHome();
        }) }, "สร้างงาน"))) : h("p", { class: "muted" }, "ต้องมีประเภทงานที่อนุมัติแล้วก่อน (เมนู ประเภทงาน)")));
}

async function staffDetail(sid) {
  const sub = await api("/submissions/" + sid);
  const mine = sub.staff_id === me.id;
  const move = (to) => act(async () => { await api("/submissions/" + sid + "/move", send("POST", { to_step: to })); staffDetail(sid); });
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · ผู้ดูแล " + sub.staff_id + " · นักวิจัย " + sub.researcher_ids.join(", ")), stepper(sub),
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", disabled: !mine || sub.current_step <= 0, onclick: move(sub.current_step - 1) }, "ย้อนกลับหนึ่งขั้น"),
        h("button", { class: "primary", type: "button", disabled: !mine || sub.current_step >= sub.step_count, onclick: move(sub.current_step + 1) }, "ไปขั้นถัดไป"),
        mine ? null : h("span", { class: "muted" }, "เฉพาะเจ้าหน้าที่ผู้ดูแลเท่านั้นที่แก้ไขได้"))),
    h("section", { class: "card" }, h("h2", {}, "ประวัติ"), sub.events.length ? sub.events.map((e) => h("p", { class: "muted" }, e.at + " · ขั้น " + (e.from_step + 1) + " → " + (e.to_step + 1) + " · " + e.staff_id + (e.note ? " · " + e.note : ""))) : h("p", { class: "muted" }, "ยังไม่มีการเปลี่ยนขั้นตอน")));
}

async function staffQueue(body, q, subs) {
  const now = new Date().toISOString(), st = staffStats(q, subs, now);
  const stat = (n, label) => h("div", { class: "stat" }, h("b", {}, String(n)), h("span", {}, label));
  body.append(...[h("h1", { class: "page-title" }, "เอกสารรอตรวจ"), h("p", { class: "muted sub" }, "เรียงจากส่งมาก่อน"),
    q.length ? h("div", { class: "stats" }, stat(st.waiting, "รอตรวจ"), stat(st.active, "งานที่กำลังดำเนินการ"), stat(st.old, "รอตรวจเกิน 7 วัน")) : null,
    q.length ? h("div", {}, q.map((u) => {
    const dismissed = new Set();
    const note = h("input", { type: "text", placeholder: "หมายเหตุถึงนักวิจัย (ไม่บังคับ)" });
    const mine = u.staff_id === me.id;
    const list = h("div");
    const draw = () => list.replaceChildren(...u.findings.map((f, i) => h("label", { class: "finding " + f.kind + (dismissed.has(i) ? " dismissed" : ""), style: "display:block" },
      h("input", { type: "checkbox", checked: dismissed.has(i), onchange: (ev) => { ev.target.checked ? dismissed.add(i) : dismissed.delete(i); draw(); } }), " ", h("b", {}, KIND[f.kind]), " · ", f.text, " ", h("span", { class: "muted" }, "(ติ๊ก = ปัดตก)"))));
    draw();
    const decide = (decision) => act(async () => { await api("/uploads/" + u.id + "/review", send("POST", { decision, dismissed: [...dismissed], note: note.value })); staffHome(); });
    const ai = u.findings.length ? h("span", { class: "badge warn" }, "AI พบ " + u.findings.length + " ข้อ") : h("span", { class: "badge ok" }, "AI ไม่พบข้อสังเกต (หรือตรวจไม่ได้)");
    return h("div", { class: "doc" }, h("div", { class: "between" }, h("span", {}, h("b", {}, u.doc_name), " ", h("span", { class: "muted" }, "· " + u.submission_title)), ai),
      h("p", { class: "muted sub" }, "ผู้ดูแล " + u.staff_id + " · ส่ง " + agoText(u.created, now)), " ",
      u.answers.length ? answersView(u) : h("a", { href: "/api/track/uploads/" + u.id + "/file", target: "_blank" }, "เปิดไฟล์ " + u.filename),
      list, note,
      h("div", { class: "actions" },
        h("button", { class: "primary", type: "button", disabled: !mine, onclick: decide("approve") }, "อนุมัติ"),
        h("button", { class: "ghost danger", type: "button", disabled: !mine, onclick: decide("return") }, "ส่งกลับให้แก้ไข"),
        mine ? null : h("span", { class: "muted" }, "เฉพาะผู้ดูแลเท่านั้น")));
  })) : h("section", { class: "card empty" }, h("span", { class: "ic" }, icon("check")), h("b", {}, "ไม่มีเอกสารรอตรวจ"), h("p", { class: "muted" }, "เมื่อนักวิจัยกดส่งเอกสาร จะแสดงที่นี่"))].filter(Boolean));
}

async function staffTypes(body) {
  const types = await api("/types");
  const name = h("input", { type: "text", placeholder: "ชื่อประเภทงาน เช่น ทุน CMU Presidential, ขอเบิกค่าเดินทาง, ขออนุมัติจริยธรรมการวิจัย" });
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: act(async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    const out = await api("/types", form({ name: name.value.trim() || file.name, file }));
    draftEditor(out.version_id);
  }) });
  body.append(
    h("section", { class: "card" }, h("h2", {}, "สร้างประเภทงานใหม่"), h("p", { class: "muted" }, "อัปโหลดคู่มือหรือประกาศของงานนั้น (ทุน เบิกจ่าย ขออนุมัติ ฯลฯ) แล้ว AI จะร่างขั้นตอนและเอกสารที่ต้องส่งให้ตรวจก่อนใช้งานจริง"), name, h("div", { class: "actions" }, pick,
      h("button", { class: "primary", type: "button", onclick: () => pick.click() }, "อัปโหลดเอกสารและให้ AI ร่างขั้นตอน"))),
    h("section", { class: "card" }, h("h2", {}, "ประเภทงานทั้งหมด"), types.map((t) => h("div", { class: "list-row" },
      h("span", {}, t.type_name, " v" + t.version, " ", h("span", { class: "muted" }, t.status === "draft" ? "ฉบับร่าง (ยังไม่ใช้งาน)" : "ใช้งานอยู่ · " + t.steps.length + " ขั้นตอน")),
      t.status === "draft" ? h("button", { class: "ghost", type: "button", onclick: () => draftEditor(t.id) }, "ตรวจและอนุมัติ")
        : h("span", { class: "tools" }, postControls(t), newVersionButton(t))))));
}

// open a type as a post researchers can start from; the owner is staff in charge of every request started from it
function postControls(t) {
  const staff = users.filter((u) => u.role === "staff");
  const publish = (owner) => api("/types/" + t.type_id + "/publish", send("POST", owner ? { owner_id: owner } : {}));
  const owner = h("select", { class: "field", "aria-label": "ผู้ดูแลงานนี้", onchange: act(async (ev) => { await publish(ev.target.value); staffHome(); }) },
    staff.map((u) => h("option", { value: u.id, selected: u.id === t.owner_id }, "ผู้ดูแล " + u.name)));
  return t.open
    ? h("span", { class: "tools" }, h("span", { class: "badge ok" }, "เปิดรับ"), owner, h("button", { class: "ghost", type: "button", onclick: act(async () => { await api("/types/" + t.type_id + "/close", { method: "POST" }); staffHome(); }) }, "ปิดรับ"))
    : h("button", { class: "ghost", type: "button", onclick: act(async () => { await publish(); staffHome(); }) }, "เปิดรับ");
}

function newVersionButton(t) {
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: act(async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    const out = await api("/types/" + t.type_id + "/versions", form({ file }));
    draftEditor(out.version_id);
  }) });
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
        h("button", { class: "ghost", type: "button", onclick: act(async () => { if (confirm("ให้ AI ร่างใหม่? การแก้ไขที่ยังไม่บันทึกจะหายไป")) { await api("/versions/" + vid + "/redraft", { method: "POST" }); draftEditor(vid); } }) }, "ให้ AI ร่างใหม่"),
        h("button", { class: "primary", type: "button", onclick: act(async () => { await save(); await api("/versions/" + vid + "/approve", { method: "POST" }); tab = "types"; staffHome(); }) }, "อนุมัติและเริ่มใช้งาน"))));
}

// ---------- chat drawer (researchers) ----------
// The old chat page, embedded: no chat code is copied and its history keeps working.
const removeChat = () => document.querySelectorAll("#chat-drawer, #chat-fab").forEach((e) => e.remove());
// one Escape listener for the page, not one per login
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") document.querySelector("#chat-drawer:not([hidden]) .chat-head button")?.click(); });

function chatDrawer() {
  removeChat();  // two overlapping logins must not leave two drawers
  const frame = h("iframe", { class: "chat-frame", title: "แชทผู้ช่วย RiSA" });
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

// ---------- start ----------
async function boot() {
  removeChat();
  try { me = await api("/me"); } catch { me = null; }
  const logout = document.getElementById("logout");
  document.getElementById("who").replaceChildren(...(me ? [h("span", { class: "av" }, me.name[0].toUpperCase()), h("span", {}, me.name, h("small", {}, ROLE[me.role]))] : []));
  logout.hidden = !me;
  document.getElementById("chatlink").hidden = !me;
  logout.onclick = async () => { await api("/logout", { method: "POST" }); start(); };
  if (!me) { tab = "queue"; return loginScreen(); }  // the next staff member starts on the inbox
  users = await api("/mock-users");
  await (me.role === "staff" ? staffHome : researcherHome)();
  if (me.role === "researcher") chatDrawer();
}

// any failed load shows an alert instead of leaving a blank page
function start() { return boot().catch(fail); }
start();
