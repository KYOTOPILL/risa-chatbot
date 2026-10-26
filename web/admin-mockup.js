// Fake data and fake actions: nothing is saved. Edit TREE to try other content.
// File = [name, size in KB, days since edit, Thai summary, downloadable through chat]
const TREE = {
  "CMU Presidential Scholarship": [
    ["1 - Living Allowance - Receipt.pdf", 182, 2, "ใบเสร็จรับเงินค่าครองชีพรายเดือน", true],
    ["2 - Book and Stationery - Receipt.pdf", 176, 2, "ใบเสร็จรับเงินค่าหนังสือและอุปกรณ์การเรียน", true],
    ["3 - Settlement Allowance - Receipt.pdf", 181, 2, "ใบเสร็จรับเงินค่าตั้งถิ่นฐาน", true],
    ["4 - Travel Allowance to CMU - Receipt.pdf", 179, 2, "ใบเสร็จรับเงินค่าเดินทางมา มช.", true],
    ["5 - Travel Allowance to Hometown - Receipt.pdf", 180, 2, "ใบเสร็จรับเงินค่าเดินทางกลับภูมิลำเนา", true],
    ["6 - Thesis Publication - Receipt.pdf", 178, 2, "ใบเสร็จรับเงินค่าตีพิมพ์วิทยานิพนธ์", true],
    ["Announcement Academic Year 2024.pdf", 840, 9, "ประกาศรับสมัครทุนการศึกษา ปีการศึกษา 2567", true],
  ],
  "TED Youth Startup": [
    ["Form-TYS Proposal V2026.docx", 64, 0, "แบบฟอร์มข้อเสนอโครงการ TED Youth Startup", true],
    ["Form-TYS Budget V2026.xlsx", 38, 0, "", false],
  ],
};
const DAYS = (d) => (d === 0 ? "วันนี้" : `${d} วันที่แล้ว`);
const KB = (n) => (n >= 1024 ? `${(n / 1024).toFixed(1)} MB` : `${n} KB`);
const FOLDER = '<svg class="fol" viewBox="0 0 36 32" aria-hidden="true"><path d="M2 6a3 3 0 0 1 3-3h8l3 4h15a3 3 0 0 1 3 3v16a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3z" fill="currentColor" opacity=".9"/></svg>';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", ...(text != null && { textContent: text }) });
const total = () => Object.values(TREE).reduce((n, f) => n + f.length, 0);

let path = null, changed = 0, busy = false, undo = null, toastTimer, newN = 0;
const selected = new Set();
let openMenu = null;

function toast(text, undoFn) {
  $("tmsg").textContent = text;
  $("undo").hidden = !undoFn;
  undo = undoFn;
  $("toast").classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 5000);
}
$("undo").onclick = () => { undo?.(); $("toast").classList.add("hidden"); };

function removeFiles(names) {
  const folder = TREE[path], gone = folder.filter((f) => names.has(f[0]));
  TREE[path] = folder.filter((f) => !names.has(f[0]));
  selected.clear(); changed += gone.length;
  toast(`ลบ ${gone.length === 1 ? gone[0][0] : gone.length + " ไฟล์"} แล้ว`, () => { TREE[path] = folder; changed -= gone.length; render(); });
  render();
}
function removeFolder(name) {
  const files = TREE[name];
  delete TREE[name]; changed += files.length;
  toast(`ลบโฟลเดอร์ ${name} แล้ว`, () => { TREE[name] = files; changed -= files.length; render(); });
  render();
}

function menu(items) {
  const wrap = el("div", "ops"), b = el("button", "dots", "⋯");
  b.type = "button"; b.setAttribute("aria-label", "เมนู"); b.setAttribute("aria-expanded", "false");
  b.onclick = (e) => {
    e.stopPropagation();
    const was = openMenu?.parentNode === wrap;
    closeMenu();
    if (was) return;
    const m = el("div", "menu");
    for (const it of items) {
      if (it === "-") { m.append(el("hr")); continue; }
      const [label, fn, cls] = it, x = el("button", cls || "", label);
      x.type = "button"; x.onclick = (ev) => { ev.stopPropagation(); closeMenu(); fn(); };
      m.append(x);
    }
    wrap.append(m); openMenu = m; b.setAttribute("aria-expanded", "true");
  };
  wrap.append(b);
  return wrap;
}
function closeMenu() { openMenu?.parentNode.firstChild.setAttribute("aria-expanded", "false"); openMenu?.remove(); openMenu = null; }
document.addEventListener("click", closeMenu);
document.addEventListener("keydown", (e) => e.key === "Escape" && closeMenu());

function head(withCheck) {
  const r = el("div", "frow head"); r.setAttribute("role", "row");
  const all = el("input"); all.type = "checkbox"; all.setAttribute("aria-label", "เลือกทั้งหมด");
  if (withCheck) {
    const names = TREE[path].map((f) => f[0]);
    all.checked = names.length > 0 && names.every((n) => selected.has(n));
    all.onchange = () => { names.forEach((n) => (all.checked ? selected.add(n) : selected.delete(n))); render(); };
  }
  const c = el("div"); if (withCheck) c.append(all);
  r.append(c, el("div", "", "ชื่อ"), el("div", "sz", "ขนาด"), el("div", "dt", "แก้ไขล่าสุด"), el("div"));
  return r;
}

function folderRow(name) {
  const files = TREE[name], r = el("div", "frow folder"), who = el("div", "who"), nm = el("div", "nm");
  who.innerHTML = FOLDER;
  nm.append(el("b", "", name), el("span", "", `${files.length} ไฟล์`));
  who.append(nm);
  const days = files.length ? Math.min(...files.map((f) => f[2])) : 0;
  r.append(el("div"), who, el("div", "sz", KB(files.reduce((n, f) => n + f[1], 0))), el("div", "dt", DAYS(days)),
    menu([["เปลี่ยนชื่อ", () => toast("ตัวอย่าง: เปลี่ยนชื่อโฟลเดอร์")], "-", ["ลบโฟลเดอร์", () => removeFolder(name), "danger"]]));
  r.onclick = () => { path = name; selected.clear(); render(); };
  return r;
}

function fileRow([name, kb, days, summary, chat]) {
  const r = el("div", "frow file"), who = el("div", "who"), nm = el("div", "nm"), box = el("input");
  box.type = "checkbox"; box.checked = selected.has(name); box.setAttribute("aria-label", `เลือก ${name}`);
  box.onchange = () => { box.checked ? selected.add(name) : selected.delete(name); render(); };
  const title = el("b", "", name);
  if (chat) title.append(el("em", "chatpill", "ดาวน์โหลดผ่านแชท"));
  nm.append(title);
  if (summary) nm.append(el("span", "", summary));
  who.append(fileIcon(name), nm);
  if (selected.has(name)) r.classList.add("sel");
  const c = el("div"); c.append(box);
  r.append(c, who, el("div", "sz", KB(kb)), el("div", "dt", DAYS(days)),
    menu([["เปลี่ยนชื่อ", () => toast("ตัวอย่าง: เปลี่ยนชื่อไฟล์")], ["ย้ายไป…", () => toast("ตัวอย่าง: เลือกโฟลเดอร์ปลายทาง")],
      ["แทนที่ไฟล์", () => toast("ตัวอย่าง: อัปโหลดไฟล์ใหม่ทับ")], "-", ["ลบ", () => removeFiles(new Set([name])), "danger"]]));
  return r;
}

function renderIndex() {
  const box = $("index"), pill = el("span", "pill"), btn = el("button", changed || busy ? "primary" : "ghost");
  box.className = `index ${busy ? "busy" : changed ? "stale" : "ok"}`;
  btn.type = "button"; btn.disabled = busy;
  btn.textContent = busy ? "กำลังอัปเดต…" : changed ? "อัปเดตดัชนีตอนนี้" : "อัปเดตดัชนีใหม่";
  btn.onclick = () => { busy = true; render(); setTimeout(() => { busy = false; changed = 0; render(); toast("อัปเดตดัชนีแล้ว"); }, 1500); };
  if (busy) pill.textContent = "กำลังอัปเดตดัชนี…";
  else if (changed) pill.innerHTML = `มี ${changed} ไฟล์เปลี่ยนแปลง <small>แชทยังใช้ข้อมูลเดิมจนกว่าจะอัปเดตดัชนี</small>`;
  else pill.innerHTML = `ดัชนีล่าสุด · ${total()} ไฟล์ <small>แชทใช้ข้อมูลล่าสุดแล้ว</small>`;
  box.replaceChildren(pill, btn);
}

function render() {
  closeMenu();
  const crumbs = $("crumbs"), root = el("button", "crumb", "เอกสารทั้งหมด");
  root.type = "button"; root.onclick = () => { path = null; selected.clear(); render(); };
  crumbs.replaceChildren(root);
  if (path) crumbs.append(el("span", "muted", "›"), el("strong", "", path));
  else root.style.fontWeight = "700";

  const list = $("list"), names = path ? TREE[path] : Object.keys(TREE);
  list.replaceChildren(head(!!path));
  if (!names.length) list.append(el("p", "empty", path ? "โฟลเดอร์นี้ยังไม่มีไฟล์" : "ยังไม่มีเอกสาร"));
  else list.append(...(path ? names.map(fileRow) : names.map(folderRow)));

  $("bulk").classList.toggle("show", selected.size > 0);
  $("bulk").inert = selected.size === 0;
  if (selected.size) $("count").textContent = `เลือก ${selected.size} ไฟล์`;
  renderIndex();
}

$("pick").onclick = () => {
  const dir = path || Object.keys(TREE)[0];
  TREE[dir].unshift([`new-document-${++newN}.pdf`, 120, 0, "", false]);
  changed++;
  toast(`อัปโหลดไปที่ ${dir} แล้ว`);
  render();
};
$("newdir").onclick = () => { TREE[`โฟลเดอร์ใหม่ ${Object.keys(TREE).length + 1}`] = []; render(); };
$("delsel").onclick = () => removeFiles(new Set(selected));
$("mvsel").onclick = () => toast("ตัวอย่าง: เลือกโฟลเดอร์ปลายทาง");
$("clear").onclick = () => { selected.clear(); render(); };
render();
