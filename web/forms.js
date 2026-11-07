// Online forms. AI drafts the fields of a document, staff edit and approve, researchers fill them in on the website.
// Uses h, api, act, send, show, fail, findings, KIND, STATUS, users, me, tab, staffHome from home.js (classic scripts share one scope).
const FIELD_TYPES = { text: "ข้อความสั้น", longtext: "ข้อความยาว", number: "ตัวเลข", date: "วันที่", choice: "ตัวเลือก", file: "แนบไฟล์" };
const FORM_STATUS = (f) => !f ? "ยังไม่มีแบบฟอร์ม" : f.status === "approved" ? "ใช้งานอยู่ · นักวิจัยกรอกในเว็บ" : "ฉบับร่าง · นักวิจัยยังไม่เห็น";

// one input for one field; get() returns the answer, a File for a new attachment, or undefined for "unchanged file"
function fieldInput(f, value, readOnly = false) {
  let el;
  if (f.type === "longtext") el = h("textarea", { rows: 3 });
  else if (f.type === "choice") el = h("select", { class: "field" }, h("option", { value: "" }, "— เลือก —"), f.options.map((o) => h("option", { value: o }, o)));
  else if (f.type === "file") el = h("input", { type: "file", accept: ".pdf,.docx,.jpg,.jpeg,.png" });
  else el = h("input", { type: f.type === "number" ? "number" : f.type === "date" ? "date" : "text", step: f.type === "number" ? "any" : null });
  if (f.type !== "file" && typeof value === "string") el.value = value;
  if (readOnly) el.disabled = true;
  const kept = f.type === "file" && value && value.name ? h("span", { class: "muted" }, "ไฟล์เดิม: " + value.name + " (เลือกไฟล์ใหม่เพื่อแทนที่)") : null;
  const box = h("label", { class: "lbl" }, h("span", {}, f.label, f.required ? h("b", { class: "req" }, " *") : null), el, f.hint ? h("small", { class: "muted" }, f.hint) : null, kept);
  box.get = () => f.type === "file" ? el.files[0] : el.value;
  return box;
}

// researcher: fill, save (AI checks the answers), send. Until it is sent the form stays editable and saving again replaces the answers.
function formFill(sub, name, def, up, reload) {
  const old = Object.fromEntries((up?.answers || []).map((a) => [a.key, a.value]));
  const inputs = def.fields.map((f) => fieldInput(f, old[f.key]));
  const save = act(async (ev) => {
    const fd = new FormData(), answers = {};
    def.fields.forEach((f, i) => {
      const v = inputs[i].get();
      if (f.type === "file") { if (v) { fd.append("file_keys", f.key); fd.append("files", v); } } else answers[f.key] = v;
    });
    fd.append("doc_name", name); fd.append("answers", JSON.stringify(answers));
    ev.target.disabled = true; ev.target.textContent = "AI กำลังตรวจ…";
    try { await api("/submissions/" + sub.id + "/forms", { method: "POST", body: fd }); } finally { reload(); }
  });
  return h("div", { class: "fillform" }, inputs, h("div", { class: "actions end" }, h("button", { class: "primary", type: "button", onclick: save }, up ? "บันทึกใหม่และให้ AI ตรวจ" : "บันทึกและให้ AI ตรวจ")));
}

// what was filled in: staff review and the researcher's own sent form
function answersView(up) {
  return h("dl", { class: "answers" }, up.answers.map((a) => h("div", {}, h("dt", { class: "muted" }, a.label),
    h("dd", {}, a.value && a.value.name ? h("a", { href: "/api/track/uploads/" + up.id + "/answer-file?key=" + encodeURIComponent(a.key), target: "_blank" }, a.value.name) : (a.value || "—")))));
}

// ---------- staff: tab แบบฟอร์ม ----------
async function staffForms(body) {
  const types = (await api("/types")).filter((t) => t.status === "approved");
  const all = await Promise.all(types.map(async (t) => [t, Object.fromEntries((await api("/types/" + t.type_id + "/forms")).map((f) => [f.doc_name, f]))]));
  const again = () => staffHome();
  const row = (t, doc, f) => h("div", { class: "list-row" },
    h("span", { class: "grow" }, h("b", {}, doc), h("span", { class: "muted block" }, FORM_STATUS(f) + (f ? " · " + f.fields.length + " ช่อง" : ""))),
    h("span", { class: "tools" },
      h("button", { class: f ? "ghost" : "primary", type: "button", onclick: act(async (ev) => {
        if (f && !confirm("ให้ AI ร่างใหม่? ฟอร์มเดิมของเอกสารนี้จะถูกแทนที่")) return;
        ev.target.disabled = true; ev.target.textContent = "AI กำลังสร้าง…";
        let out;
        try { out = await api("/types/" + t.type_id + "/forms/draft", send("POST", { doc_name: doc })); } catch (e) { again(); throw e; }
        formEditor(t, { ...out, doc_name: doc });
      }) }, f ? "ให้ AI ร่างใหม่" : "ให้ AI สร้างฟอร์ม"),
      f ? h("button", { class: "ghost", type: "button", onclick: () => formEditor(t, f) }, "แก้ไข") : null,
      f && f.status === "draft" ? h("button", { class: "primary", type: "button", onclick: act(async () => { await api("/types/" + t.type_id + "/forms/approve", send("POST", { doc_name: doc })); again(); }) }, "อนุมัติ") : null));
  body.append(...[h("h1", { class: "page-title" }, "แบบฟอร์ม"),
    h("p", { class: "muted sub" }, "AI ร่างช่องกรอกจากคู่มือของประเภทงาน เจ้าหน้าที่แก้ไขและอนุมัติ นักวิจัยกรอกและแนบไฟล์ในเว็บ เอกสารที่ไม่มีฟอร์มยังอัปโหลดไฟล์ตามเดิม"),
    all.length ? all.map(([t, by]) => {
      const docs = [...new Set(t.steps.flatMap((s) => s.documents))];
      return h("section", { class: "card" }, h("h2", {}, t.type_name), docs.length ? docs.map((d) => row(t, d, by[d])) : h("p", { class: "muted" }, "ประเภทงานนี้ไม่มีเอกสารที่ต้องส่ง"));
    }) : h("section", { class: "card empty" }, h("b", {}, "ยังไม่มีประเภทงานที่อนุมัติ"), h("p", { class: "muted" }, "สร้างและอนุมัติประเภทงานก่อน (เมนู ประเภทงาน)"))].flat());
}

// Editor: one line per question, settings of the selected line in a side panel; แก้ไข and ตัวอย่าง are two tabs.
const CHIP = { text: "", longtext: "", number: "num", date: "date", choice: "ch", file: "file" };
function formEditor(t, f, preview = false, sel = 0) {
  const fields = f.fields.map((x) => ({ ...x, options: x.options?.length ? [...x.options] : [] }));
  let title = f.title;
  sel = Math.min(sel, fields.length - 1);
  const keep = () => ({ ...f, title, fields: fields.filter((x) => x.label.trim()) });
  const save = (approve) => act(async () => {
    await api("/types/" + t.type_id + "/forms", send("PUT", { doc_name: f.doc_name, title, fields: keep().fields }));
    if (approve) await api("/types/" + t.type_id + "/forms/approve", send("POST", { doc_name: f.doc_name }));
    staffHome();
  });
  const seg = h("span", { class: "seg" },
    h("button", { type: "button", class: preview ? "" : "on", onclick: () => preview && formEditor(t, keep(), false, sel) }, "แก้ไข"),
    h("button", { type: "button", class: preview ? "on" : "", onclick: () => !preview && formEditor(t, keep(), true, sel) }, "ตัวอย่าง"));
  const top = (right) => h("div", { class: "formbar" }, h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"), seg, h("span", { class: "tools" }, right));
  if (preview) {
    show(top(null), h("section", { class: "card pv" }, h("span", { class: "badge warn" }, "ตัวอย่าง: นักวิจัยจะเห็นแบบนี้"), h("h2", {}, title),
      h("div", { class: "fillform" }, fields.filter((x) => x.label.trim()).map((x) => fieldInput(x, undefined, true)))));
    return;
  }
  const status = f.status === "approved" ? "ใช้งานอยู่ การบันทึกมีผลกับนักวิจัยทันที" : "ฉบับร่าง นักวิจัยยังไม่เห็นจนกว่าจะอนุมัติ";
  const list = h("div", { class: "card qlist" }), panel = h("div", { class: "card qpanel" }), labels = [];
  const go = (i) => { sel = i; draw(); };
  const swap = (i, j) => { [fields[i], fields[j]] = [fields[j], fields[i]]; go(j); };
  const drawList = () => {
    labels.length = 0;
    list.replaceChildren(h("div", { class: "qrow head" }, h("span", {}, "#"), h("span", {}, "ช่อง"), h("span", {}, "ชนิด"), h("span", {}, "จำเป็น")),
      ...fields.map((x, i) => {
        const lab = h("span", { class: "qlabel" }, x.label || "(ยังไม่ตั้งชื่อ)");
        labels.push(lab);
        return h("button", { type: "button", class: "qrow" + (i === sel ? " sel" : ""), onclick: () => go(i) },
          h("span", { class: "n" }, String(i + 1)), lab, h("span", { class: "qkind " + CHIP[x.type] }, FIELD_TYPES[x.type]), x.required ? h("span", { class: "reqmark" }, "จำเป็น") : h("span", { class: "dim" }, "ไม่จำเป็น"));
      }),
      h("button", { type: "button", class: "qadd", onclick: () => { fields.push({ label: "", hint: "", type: "text", required: false, options: [] }); go(fields.length - 1); } }, "+ เพิ่มช่อง"));
  };
  const drawPanel = () => {
    const x = fields[sel];
    if (!x) { panel.replaceChildren(h("p", { class: "muted" }, "ยังไม่มีช่อง กด “+ เพิ่มช่อง”")); return; }
    panel.replaceChildren(...[h("h3", {}, "ช่องที่ " + (sel + 1)),
      h("label", { class: "lbl" }, h("span", {}, "ชื่อช่อง"), h("input", { type: "text", value: x.label, oninput: (e) => { x.label = e.target.value; labels[sel].textContent = x.label || "(ยังไม่ตั้งชื่อ)"; } })),
      h("label", { class: "lbl" }, h("span", {}, "คำอธิบายใต้ช่อง (ไม่บังคับ)"), h("input", { type: "text", value: x.hint || "", oninput: (e) => { x.hint = e.target.value; } })),
      h("div", { class: "lbl" }, h("span", {}, "ชนิด"), h("div", { class: "types" }, Object.entries(FIELD_TYPES).map(([k, v]) => h("button", { type: "button", class: k === x.type ? "on" : "",
        onclick: () => { x.type = k; if (k === "choice" && x.options.length < 2) x.options = ["ตัวเลือก 1", "ตัวเลือก 2"]; drawList(); drawPanel(); } }, v)))),
      x.type === "choice" ? h("div", { class: "lbl" }, h("span", {}, "ตัวเลือก"), x.options.map((o, j) => h("div", { class: "optrow" }, h("span", { class: "dot" }),
        h("input", { type: "text", value: o, "aria-label": "ตัวเลือก " + (j + 1), oninput: (e) => { x.options[j] = e.target.value; } }),
        h("button", { class: "ghost", type: "button", "aria-label": "ลบตัวเลือก", onclick: () => { x.options.splice(j, 1); drawPanel(); } }, "×"))),
        h("button", { class: "ghost", type: "button", onclick: () => { x.options.push(""); drawPanel(); } }, "+ เพิ่มตัวเลือก")) : null,
      h("label", { class: "tog" }, h("span", {}, "จำเป็นต้องกรอก"), h("input", { type: "checkbox", class: "swx", checked: !!x.required, onchange: (e) => { x.required = e.target.checked; drawList(); } })),
      h("div", { class: "tog" },
        h("button", { class: "ghost danger", type: "button", onclick: () => { fields.splice(sel, 1); sel = Math.min(sel, fields.length - 1); draw(); } }, "ลบช่องนี้"),
        h("span", { class: "tools" },
          h("button", { class: "ghost", type: "button", "aria-label": "เลื่อนขึ้น", disabled: sel === 0, onclick: () => swap(sel, sel - 1) }, "↑"),
          h("button", { class: "ghost", type: "button", "aria-label": "เลื่อนลง", disabled: sel === fields.length - 1, onclick: () => swap(sel, sel + 1) }, "↓"),
          h("button", { class: "ghost", type: "button", onclick: () => { fields.splice(sel + 1, 0, { ...x, options: [...x.options], key: undefined }); go(sel + 1); } }, "ทำซ้ำ")))].filter(Boolean));
  };
  const draw = () => { drawList(); drawPanel(); };
  draw();
  show(top([h("button", { class: "ghost", type: "button", onclick: save(false) }, "บันทึก"), f.status === "draft" ? h("button", { class: "primary", type: "button", onclick: save(true) }, "บันทึกและอนุมัติ") : null]),
    h("div", { class: "qtitle" }, h("input", { class: "formtitle", type: "text", value: title, "aria-label": "ชื่อแบบฟอร์ม", oninput: (e) => { title = e.target.value; } }),
      h("p", { class: "muted sub" }, f.doc_name + " · " + t.type_name + " · " + status + " · " + fields.length + " ช่อง")),
    h("div", { class: "qgrid" }, list, panel));
}
