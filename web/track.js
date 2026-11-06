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

function show(...nodes) { app.replaceChildren(...nodes); }
function fail(e) { alert(e.message); }
const act = (fn) => async (ev) => { try { await fn(ev); } catch (e) { fail(e); } };

// ---------- login ----------
async function loginScreen() {
  users = await api("/mock-users");
  show(h("section", { class: "card" },
    h("h2", {}, "เข้าสู่ระบบ (ระบบจำลอง)"),
    h("p", { class: "muted" }, "ตอนนี้เป็นบัญชีทดลอง ภายหลังจะเปลี่ยนเป็นบัญชีอีเมล CMU"),
    users.map((u) => h("div", { class: "list-row" },
      h("span", {}, u.name, " ", h("span", { class: "muted" }, ROLE[u.role] + " · " + u.id)),
      h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/login", send("POST", { user_id: u.id })); start(); }) }, "เข้าสู่ระบบ")))));
}

// ---------- shared: stepper ----------
function stepper(sub) {
  const done = (i) => sub.events.filter((e) => e.to_step > i && e.from_step <= i).map((e) => e.at.slice(0, 10)).pop();
  return h("ol", { class: "steps" }, sub.steps.map((s, i) => {
    const cls = i < sub.current_step ? "done" : i === sub.current_step ? "now" : "next";
    const mark = cls === "done" ? "✅" : cls === "now" ? "🔵" : "⚪";
    return h("li", { class: cls }, mark, h("span", {}, (i + 1) + ". " + s.title), cls === "done" && done(i) ? h("span", { class: "muted" }, done(i)) : null);
  }));
}

function findings(list, dismissed = []) {
  return list.map((f, i) => h("div", { class: "finding " + f.kind + (dismissed.includes(i) ? " dismissed" : "") }, h("b", {}, KIND[f.kind] || f.kind), " · ", f.text));
}

// ---------- researcher ----------
async function researcherHome() {
  const subs = await api("/submissions");
  show(h("section", { class: "card" }, h("h2", {}, "งานของฉัน"),
    subs.length ? subs.map((s) => h("div", { class: "list-row" },
      h("span", {}, s.title, " ", h("span", { class: "muted" }, s.type_name + " · ขั้นที่ " + Math.min(s.current_step + 1, s.step_count) + "/" + s.step_count + (s.current_step >= s.step_count ? " (เสร็จสิ้น)" : ""))),
      h("button", { class: "ghost", type: "button", onclick: () => researcherDetail(s.id) }, "ดูความคืบหน้า")))
      : h("p", { class: "muted" }, "ยังไม่มีงานที่เจ้าหน้าที่สร้างให้")));
}

async function researcherDetail(sid) {
  const sub = await api("/submissions/" + sid);
  const step = sub.steps[sub.current_step];
  const staff = users.find((u) => u.id === sub.staff_id);
  const docs = step ? step.documents.map((name) => {
    const up = sub.uploads.find((u) => u.doc_name === name);
    const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: act(async (ev) => {
      const file = ev.target.files[0];
      if (!file) return;
      await api("/submissions/" + sid + "/uploads", form({ doc_name: name, file }));
      researcherDetail(sid);
    }) });
    const canSend = up && (up.status === "screened" || up.status === "cannot_check");
    return h("div", { class: "doc" }, h("b", {}, name), " ", up ? h("span", { class: "muted" }, STATUS[up.status]) : h("span", { class: "muted" }, "ยังไม่ได้ส่ง"),
      up ? findings(up.findings) : null,
      up && up.status === "returned" ? h("p", { class: "err" }, "เจ้าหน้าที่ส่งกลับ: " + (up.note || "(ไม่มีหมายเหตุ)")) : null,
      h("div", { class: "row" }, pick,
        h("button", { class: "ghost", type: "button", onclick: () => pick.click() }, up ? "อัปโหลดใหม่" : "อัปโหลดไฟล์ (.pdf / .docx)"),
        canSend ? h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/uploads/" + up.id + "/send", { method: "POST" }); researcherDetail(sid); }) }, "ส่งให้เจ้าหน้าที่ตรวจ") : null));
  }) : [];
  show(h("button", { class: "ghost", type: "button", onclick: researcherHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · เจ้าหน้าที่ผู้ดูแล: " + (staff ? staff.name : sub.staff_id)), stepper(sub)),
    step ? h("section", { class: "card" }, h("h2", {}, "เอกสารสำหรับขั้นตอนนี้"), docs.length ? docs : h("p", { class: "muted" }, "ขั้นตอนนี้ไม่ต้องส่งเอกสาร"))
      : h("section", { class: "card" }, h("p", {}, "งานนี้เสร็จสิ้นแล้ว")));
}

// ---------- staff ----------
let tab = "subs";
function staffHome() {
  const tabs = [["subs", "งานทั้งหมด"], ["queue", "รอตรวจเอกสาร"], ["types", "ประเภทงานและขั้นตอน"]];
  const body = h("div");
  const nav = h("nav", { class: "tabs" }, tabs.map(([id, label]) => h("button", { class: "ghost", type: "button", "aria-current": String(id === tab), onclick: () => { tab = id; staffHome(); } }, label)));
  show(nav, body);
  ({ subs: staffSubs, queue: staffQueue, types: staffTypes })[tab](body).catch(fail);
}

async function staffSubs(body) {
  const [subs, types] = await Promise.all([api("/submissions"), api("/types")]);
  const approved = types.filter((t) => t.status === "approved");
  const title = h("input", { type: "text", placeholder: "ชื่องาน เช่น ทุน CMU - สมชาย" });
  const type = h("select", { class: "field" }, approved.map((t) => h("option", { value: t.id }, t.type_name + " (v" + t.version + ")")));
  const researchers = users.filter((u) => u.role === "researcher").map((u) => h("label", { class: "check" }, h("input", { type: "checkbox", value: u.id }), " " + u.name));
  const staffSel = h("select", { class: "field" }, users.filter((u) => u.role === "staff").map((u) => h("option", { value: u.id, selected: u.id === me.id }, u.name)));
  body.append(
    h("section", { class: "card" }, h("h2", {}, "งานทั้งหมด"),
      subs.map((s) => h("div", { class: "list-row" },
        h("span", {}, s.title, " ", h("span", { class: "muted" }, s.type_name + " · ขั้น " + Math.min(s.current_step + 1, s.step_count) + "/" + s.step_count + " · ผู้ดูแล " + s.staff_id + " · นักวิจัย " + s.researcher_ids.join(", "))),
        h("button", { class: "ghost", type: "button", onclick: () => staffDetail(s.id) }, "เปิด")))),
    h("section", { class: "card" }, h("h2", {}, "สร้างงานใหม่ให้นักวิจัย"),
      approved.length ? h("div", { class: "stepedit" }, title, type, h("div", { class: "checks" }, researchers), staffSel,
        h("button", { class: "primary", type: "button", onclick: act(async () => {
          const ids = [...body.querySelectorAll(".checks input:checked")].map((c) => c.value);
          await api("/submissions", send("POST", { title: title.value.trim(), version_id: +type.value, researcher_ids: ids, staff_id: staffSel.value }));
          staffHome();
        }) }, "สร้างงาน")) : h("p", { class: "muted" }, "ต้องมีประเภทงานที่อนุมัติแล้วก่อน (แท็บ ประเภทงานและขั้นตอน)")));
}

async function staffDetail(sid) {
  const sub = await api("/submissions/" + sid);
  const mine = sub.staff_id === me.id;
  const move = (to) => act(async () => { await api("/submissions/" + sid + "/move", send("POST", { to_step: to })); staffDetail(sid); });
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, sub.title), h("p", { class: "muted" }, sub.type_name + " · ผู้ดูแล " + sub.staff_id + " · นักวิจัย " + sub.researcher_ids.join(", ")), stepper(sub),
      h("div", { class: "row" },
        h("button", { class: "ghost", type: "button", disabled: !mine || sub.current_step <= 0, onclick: move(sub.current_step - 1) }, "ย้อนกลับหนึ่งขั้น"),
        h("button", { class: "primary", type: "button", disabled: !mine || sub.current_step >= sub.step_count, onclick: move(sub.current_step + 1) }, "ไปขั้นถัดไป"),
        mine ? null : h("span", { class: "muted" }, "เฉพาะเจ้าหน้าที่ผู้ดูแลเท่านั้นที่แก้ไขได้"))),
    h("section", { class: "card" }, h("h2", {}, "ประวัติ"), sub.events.length ? sub.events.map((e) => h("p", { class: "muted" }, e.at + " · ขั้น " + (e.from_step + 1) + " → " + (e.to_step + 1) + " · " + e.staff_id + (e.note ? " · " + e.note : ""))) : h("p", { class: "muted" }, "ยังไม่มีการเปลี่ยนขั้นตอน")));
}

async function staffQueue(body) {
  const q = await api("/review-queue");
  body.append(h("section", { class: "card" }, h("h2", {}, "เอกสารรอตรวจ"), q.length ? q.map((u) => {
    const dismissed = new Set();
    const note = h("input", { type: "text", placeholder: "หมายเหตุถึงนักวิจัย (ไม่บังคับ)" });
    const mine = u.staff_id === me.id;
    const list = h("div");
    const draw = () => list.replaceChildren(...u.findings.map((f, i) => h("label", { class: "finding " + f.kind + (dismissed.has(i) ? " dismissed" : ""), style: "display:block" },
      h("input", { type: "checkbox", checked: dismissed.has(i), onchange: (ev) => { ev.target.checked ? dismissed.add(i) : dismissed.delete(i); draw(); } }), " ", h("b", {}, KIND[f.kind]), " · ", f.text, " ", h("span", { class: "muted" }, "(ติ๊ก = ปัดตก)"))));
    draw();
    const decide = (decision) => act(async () => { await api("/uploads/" + u.id + "/review", send("POST", { decision, dismissed: [...dismissed], note: note.value })); staffHome(); });
    return h("div", { class: "doc" }, h("b", {}, u.doc_name), " ", h("span", { class: "muted" }, u.submission_title + " · ผู้ดูแล " + u.staff_id), " ",
      h("a", { href: "/api/track/uploads/" + u.id + "/file", target: "_blank" }, "เปิดไฟล์ " + u.filename),
      u.status === "cannot_check" ? h("p", { class: "muted" }, "AI ตรวจไม่ได้") : null, list, note,
      h("div", { class: "row" },
        h("button", { class: "primary", type: "button", disabled: !mine, onclick: decide("approve") }, "อนุมัติ"),
        h("button", { class: "ghost danger", type: "button", disabled: !mine, onclick: decide("return") }, "ส่งกลับให้แก้ไข"),
        mine ? null : h("span", { class: "muted" }, "เฉพาะผู้ดูแลเท่านั้น")));
  }) : h("p", { class: "muted" }, "ไม่มีเอกสารรอตรวจ")));
}

async function staffTypes(body) {
  const types = await api("/types");
  const name = h("input", { type: "text", placeholder: "ชื่อประเภทงาน เช่น ทุน CMU Presidential" });
  const pick = h("input", { type: "file", accept: ".pdf,.docx", hidden: true, onchange: act(async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    const out = await api("/types", form({ name: name.value.trim() || file.name, file }));
    draftEditor(out.version_id);
  }) });
  body.append(
    h("section", { class: "card" }, h("h2", {}, "สร้างประเภทงานใหม่"), h("p", { class: "muted" }, "อัปโหลดเอกสารของทุน แล้ว AI จะร่างขั้นตอนให้ตรวจก่อนใช้งานจริง"), name, h("div", { class: "row" }, pick,
      h("button", { class: "primary", type: "button", onclick: () => pick.click() }, "อัปโหลดเอกสารและให้ AI ร่างขั้นตอน"))),
    h("section", { class: "card" }, h("h2", {}, "ประเภทงานทั้งหมด"), types.map((t) => h("div", { class: "list-row" },
      h("span", {}, t.type_name, " v" + t.version, " ", h("span", { class: "muted" }, t.status === "draft" ? "ฉบับร่าง (ยังไม่ใช้งาน)" : "ใช้งานอยู่ · " + t.steps.length + " ขั้นตอน")),
      t.status === "draft" ? h("button", { class: "ghost", type: "button", onclick: () => draftEditor(t.id) }, "ตรวจและอนุมัติ") : newVersionButton(t)))));
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
      h("b", {}, "ขั้นที่ " + (i + 1)), s.unsure ? h("span", { class: "muted" }, "⚠ AI ไม่แน่ใจ ตรวจสอบก่อนอนุมัติ") : null,
      s.page ? h("span", { class: "muted" }, "มาจากหน้า " + s.page + " ของเอกสาร") : null, title, docs,
      h("button", { class: "ghost danger", type: "button", onclick: () => { steps.splice(i, 1); draw(); } }, "ลบขั้นตอนนี้"));
  }));
  draw();
  const save = () => api("/versions/" + vid, send("PUT", { steps: steps.filter((s) => s.title.trim()) }));
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("section", { class: "card" }, h("h2", {}, v.type_name + " v" + v.version + " (ฉบับร่าง)"),
      h("p", { class: "muted" }, "ยังไม่ใช้งานจริงจนกว่าจะกดอนุมัติ"), box,
      h("div", { class: "row" },
        h("button", { class: "ghost", type: "button", onclick: () => { steps.push({ title: "", documents: [], page: null, unsure: false }); draw(); } }, "+ เพิ่มขั้นตอน"),
        h("button", { class: "ghost", type: "button", onclick: act(async () => { if (confirm("ให้ AI ร่างใหม่? การแก้ไขที่ยังไม่บันทึกจะหายไป")) { await api("/versions/" + vid + "/redraft", { method: "POST" }); draftEditor(vid); } }) }, "ให้ AI ร่างใหม่"),
        h("button", { class: "primary", type: "button", onclick: act(async () => { await save(); await api("/versions/" + vid + "/approve", { method: "POST" }); tab = "types"; staffHome(); }) }, "อนุมัติและเริ่มใช้งาน"))));
}

// ---------- start ----------
async function start() {
  try { me = await api("/me"); } catch { me = null; }
  const logout = document.getElementById("logout");
  document.getElementById("who").textContent = me ? me.name + " · " + ROLE[me.role] : "";
  logout.hidden = !me;
  logout.onclick = async () => { await api("/logout", { method: "POST" }); start(); };
  if (!me) return loginScreen().catch(fail);
  users = await api("/mock-users");
  (me.role === "staff" ? staffHome : researcherHome)();
}
start();
