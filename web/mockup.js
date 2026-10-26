// Edit SCRIPT to try out wording and layout. Same classes as the real chat (style.css) (the chat design, now live in the real chat too).
// A file is [name, Thai summary, size]. The real API sends only id and name today: summary and size would be added to /api/chat.
const R = "1 - Living Allowance - Receipt.pdf", SUM = "ใบเสร็จรับเงินค่าครองชีพรายเดือนสำหรับนักศึกษาทุน ใช้แนบประกอบการเบิกจ่าย";
const SCRIPT = [
  ["user", "10:41", "ขอใบเสร็จค่าครองชีพ"],
  ["bot", "10:41", "นี่คือไฟล์ที่เกี่ยวข้องค่ะ", [[R, SUM, "182 KB"]]],
  ["user", "10:42", "ขอใบเสร็จทั้งหมด"],
  ["bot", "10:42", "นี่คือใบเสร็จทั้งหมดค่ะ", [
    [R, SUM, "182 KB"],
    ["2 - Book and Stationery - Receipt.pdf", "ใบเสร็จรับเงินค่าหนังสือและอุปกรณ์การเรียน", "176 KB"],
    ["3 - Settlement Allowance - Receipt.pdf", "ใบเสร็จรับเงินค่าตั้งถิ่นฐานสำหรับนักศึกษาที่ย้ายเข้ามาใหม่", "181 KB"],
    ["4 - Travel Allowance to CMU - Receipt.pdf", "ใบเสร็จรับเงินค่าเดินทางมามหาวิทยาลัยเชียงใหม่", "179 KB"]]],
  ["user", "10:43", "มีเอกสารประเภทอื่นไหม"],
  ["bot", "10:43", "นี่คือไฟล์หลายประเภทค่ะ", [
    ["expense-claim-th.docx", "แบบฟอร์มเบิกค่าใช้จ่ายภาษาไทย", "38 KB"],
    ["budget-2026.xlsx", "ตารางงบประมาณประจำปี 2569", "92 KB"],
    ["kickoff-slides.pptx", "สไลด์ประชุมเริ่มโครงการ", "1.4 MB"],
    ["vendor-notes.md", "", "4 KB"]]],
  ["user", "10:44", "ผู้สมัครต้องมีคะแนน IELTS เท่าไหร่"],
  ["bot", "10:44", "ต้องมีคะแนน IELTS อย่างน้อย 6.0 ค่ะ"],
  ["user", "10:45", "ขอไฟล์ใบลา"],
  ["bot", "10:45", "ขออภัย ไม่พบข้อมูลที่เกี่ยวข้องในเอกสาร กรุณาติดต่อ HR"],
  ["bot", "10:46", "ขออภัย ระบบขัดข้อง กรุณาลองใหม่อีกครั้งหรือติดต่อผู้ดูแลระบบ", [], true],
];
const STATUS = ["กำลังค้นหาเอกสาร", "กำลังหาไฟล์", "กำลังเตรียมคำตอบ"];
const DOWNLOAD = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 4v10m0 0-4-4m4 4 4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", ...(text != null && { textContent: text }) });

function row(role, time, bubble) {
  const r = el("div", `row ${role}`), stack = el("div", "stack");
  stack.append(bubble, el("div", "time", time));
  if (role === "bot") r.append(el("div", "avatar", "RiSA"));
  r.append(stack);
  return r;
}

function card([name, summary, size]) {
  const a = el("a", "fcard");
  a.href = "#";
  const body = el("div", "fbody");
  body.append(el("div", "fname", name));
  if (summary) body.append(el("div", "fsum", summary));
  body.append(el("div", "fmeta", `${name.split(".").pop().toUpperCase()} · ${size}`));
  const dl = el("span", "fdl");
  dl.innerHTML = DOWNLOAD;
  a.append(fileIcon(name), body, dl);
  return a;
}

const log = document.getElementById("log");
for (const [role, time, text, files = [], err = false] of SCRIPT) {
  const msg = el("div", `msg ${role}${err ? " err" : ""}`, text);
  if (files.length) {
    const cards = el("div", "cards");
    cards.append(...files.map(card));
    msg.append(cards);
  }
  log.append(row(role, time, msg));
}

const msg = el("div", "msg bot"), status = el("span", "waiting");
status.innerHTML = '<span class="typing"><i></i><i></i><i></i></span><span></span>';
msg.append(status);
log.append(row("bot", "", msg));
let i = 0;
(function tick() {
  status.lastChild.textContent = STATUS[i++ % STATUS.length] + "...";
  setTimeout(tick, 1800);
})();
