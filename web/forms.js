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

function formEditor(t, f) {
  const fields = f.fields.map((x) => ({ ...x }));
  let title = f.title;
  const list = h("div"), preview = h("div", { class: "fillform" });
  const draw = () => {
    list.replaceChildren(...fields.map((x, i) => h("div", { class: "fieldedit" },
      h("div", { class: "fe-top" },
        h("input", { type: "text", value: x.label, placeholder: "ชื่อช่อง", "aria-label": "ชื่อช่อง " + (i + 1), oninput: (e) => { x.label = e.target.value; drawPreview(); } }),
        h("select", { class: "field", "aria-label": "ชนิดช่อง " + (i + 1), onchange: (e) => { x.type = e.target.value; x.options ||= []; draw(); } },
          Object.entries(FIELD_TYPES).map(([k, v]) => h("option", { value: k, selected: k === x.type }, v))),
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!x.required, onchange: (e) => { x.required = e.target.checked; drawPreview(); } }), " จำเป็น")),
      h("input", { type: "text", value: x.hint || "", placeholder: "คำอธิบายใต้ช่อง (ไม่บังคับ)", "aria-label": "คำอธิบาย " + (i + 1), oninput: (e) => { x.hint = e.target.value; drawPreview(); } }),
      x.type === "choice" ? h("input", { type: "text", value: (x.options || []).join(", "), placeholder: "ตัวเลือก คั่นด้วยจุลภาค เช่น ชั้นประหยัด, ชั้นธุรกิจ", "aria-label": "ตัวเลือก " + (i + 1),
        oninput: (e) => { x.options = e.target.value.split(",").map((o) => o.trim()).filter(Boolean); drawPreview(); } }) : null,
      h("div", { class: "tools" },
        h("button", { class: "ghost", type: "button", "aria-label": "เลื่อนขึ้น", disabled: i === 0, onclick: () => { [fields[i - 1], fields[i]] = [fields[i], fields[i - 1]]; draw(); } }, "↑"),
        h("button", { class: "ghost", type: "button", "aria-label": "เลื่อนลง", disabled: i === fields.length - 1, onclick: () => { [fields[i + 1], fields[i]] = [fields[i], fields[i + 1]]; draw(); } }, "↓"),
        h("button", { class: "ghost danger", type: "button", onclick: () => { fields.splice(i, 1); draw(); } }, "ลบช่อง")))));
    drawPreview();
  };
  const drawPreview = () => preview.replaceChildren(...fields.filter((x) => x.label.trim()).map((x) => fieldInput({ ...x, options: x.options || [] }, undefined, true)));
  const save = (approve) => act(async () => {
    await api("/types/" + t.type_id + "/forms", send("PUT", { doc_name: f.doc_name, title, fields: fields.filter((x) => x.label.trim()) }));
    if (approve) await api("/types/" + t.type_id + "/forms/approve", send("POST", { doc_name: f.doc_name }));
    staffHome();
  });
  draw();
  show(h("button", { class: "ghost", type: "button", onclick: staffHome }, "← กลับ"),
    h("div", { class: "editgrid" },
      h("section", { class: "card" }, h("h2", {}, f.doc_name), h("p", { class: "muted sub" }, t.type_name + " · " + (f.status === "approved" ? "ใช้งานอยู่ การบันทึกมีผลกับนักวิจัยทันที" : "ฉบับร่าง นักวิจัยยังไม่เห็นจนกว่าจะอนุมัติ")),
        h("label", { class: "lbl" }, h("span", {}, "ชื่อแบบฟอร์ม"), h("input", { type: "text", value: title, oninput: (e) => { title = e.target.value; } })), list,
        h("div", { class: "actions" },
          h("button", { class: "ghost", type: "button", onclick: () => { fields.push({ label: "", hint: "", type: "text", required: false, options: [] }); draw(); } }, "+ เพิ่มช่อง"),
          h("button", { class: "ghost", type: "button", onclick: save(false) }, "บันทึก"),
          f.status === "draft" ? h("button", { class: "primary", type: "button", onclick: save(true) }, "บันทึกและอนุมัติ") : null)),
      h("section", { class: "card" }, h("h2", {}, "ตัวอย่างที่นักวิจัยเห็น"), h("p", { class: "muted sub" }, "ตัวอย่างอัปเดตตามที่แก้ไข"), preview)));
}
