const $ = (id) => document.getElementById(id);
const SHARE = "shareable", ROOT_LABEL = "เอกสารทั้งหมด";
let files = [], folders = [], cwd = "", selected = new Set(), dragging = [];
let timer, busy = false, stale = false;
let pending = null;  // delete waiting out its undo window: { paths, timer }
const CACHE = "risa-admin";
const vt = (fn) => (document.startViewTransition ? document.startViewTransition(fn) : fn());

const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const kb = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
const byPath = (p) => files.find((f) => f.path === p);
const visible = () => files.filter((f) => f.folder === cwd);

function say(text, err = false) { const m = $("msg"); m.textContent = text; m.className = "status" + (err ? " err" : ""); }

async function call(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "เกิดข้อผิดพลาด (" + res.status + ")");
  return data;
}

// every change saves at once; the index catches up after a short quiet period
async function mutate(url, opts) { const r = await call(url, opts); scheduleReindex(); return r; }

function scheduleReindex() {
  stale = true; clearTimeout(timer); timer = setTimeout(reindex, 2500);
  say("บันทึกแล้ว · กำลังรออัปเดตดัชนี…");
}

async function reindex() {
  clearTimeout(timer);
  if (busy) return scheduleReindex();
  busy = true; stale = false;
  say("กำลังอัปเดตดัชนี... (แชทจะรอสักครู่)");
  try {
    const r = await call("/api/admin/reindex", { method: "POST" });
    if (!stale) say("อัปเดตดัชนีแล้ว " + r.indexed + " ไฟล์" + (r.skipped.length ? " · ข้าม " + r.skipped.length + " ไฟล์: " + r.skipped.join(", ") : ""), r.skipped.length > 0);
  } catch (e) { stale = true; say(e.message, true); } finally { busy = false; }
}

async function run(fn) {
  try { await fn(); } catch (e) { say(e.message, true); }
  await load().catch((e) => say(e.message, true));
}

async function load() {
  const [f, d] = await Promise.all([call("/api/admin/files"), call("/api/admin/folders")]);
  try { sessionStorage.setItem(CACHE, JSON.stringify([f, d])); } catch (_) {}
  apply(f, d);
}

function apply(f, d) {
  const hidden = new Set(pending?.paths);
  files = f.filter((r) => !hidden.has(r.path)).map((r) => {
    const parts = r.path.split("/"), dirs = parts.slice(0, -1).filter((x) => x !== SHARE);
    return { ...r, folder: dirs[0] || "", name: parts.at(-1) };
  });
  folders = d;
  if (cwd && !folders.includes(cwd)) cwd = "";
  const have = new Set(files.map((x) => x.path));
  selected = new Set([...selected].filter((p) => have.has(p)));
  render();
}

function open(folder) { vt(() => { cwd = folder; selected.clear(); render(); }); }

function render() {
  const crumbs = $("crumbs");
  crumbs.replaceChildren(crumb(ROOT_LABEL, ""));
  if (cwd) crumbs.append(" / ", el("strong", { textContent: cwd }), folderOps(cwd));
  const body = $("rows"), here = visible().sort((a, b) => a.name.localeCompare(b.name));
  body.replaceChildren();
  if (!cwd) folders.forEach((d) => body.append(folderRow(d)));
  here.forEach((f) => body.append(fileRow(f)));
  $("empty").classList.toggle("hidden", body.children.length > 0);
  $("all").checked = here.length > 0 && here.every((f) => selected.has(f.path));
  $("sel").classList.toggle("hidden", !selected.size);
  $("selcount").textContent = "เลือก " + selected.size + " ไฟล์";
}

function crumb(label, folder) {
  const b = el("button", { className: "crumb", type: "button", textContent: label, onclick: () => open(folder) });
  dropTarget(b, folder);
  return b;
}

function folderRow(d) {
  const tr = el("tr", { className: "folder", onclick: () => open(d) });
  tr.append(el("td"), el("td", { colSpan: 4, textContent: "📁 " + d }), el("td", { className: "ops" }, folderOps(d)));
  dropTarget(tr, d);
  return tr;
}

function fileRow(f) {
  const tr = el("tr", { className: selected.has(f.path) ? "sel" : "", draggable: true,
    title: f.supported ? f.path : f.path + " · ชนิดไฟล์นี้ระบบไม่อ่าน" });
  const cb = el("input", { type: "checkbox", checked: selected.has(f.path), onchange: () => {
    cb.checked ? selected.add(f.path) : selected.delete(f.path); render(); } });
  const name = el("td", { className: "name", textContent: "📄 " + f.name, ondblclick: () => rename(f, name) });
  const share = el("input", { type: "checkbox", className: "switch", checked: f.downloadable, title: "ให้ดาวน์โหลดผ่านแชทได้",
    onchange: () => run(() => mutate("/api/admin/move", json({ path: f.path, downloadable: share.checked }))) });
  tr.append(el("td", {}, cb), name, el("td", {}, share), el("td", { textContent: kb(f.size) }), el("td", { textContent: f.mtime }),
    el("td", { className: "ops" },
      el("button", { className: "link", type: "button", textContent: "เปลี่ยนชื่อ", onclick: () => rename(f, name) }),
      el("button", { className: "link", type: "button", textContent: "แทนที่", title: "อัปโหลดไฟล์เวอร์ชันใหม่ทับไฟล์นี้", onclick: () => replacing(f) }),
      el("button", { className: "del", type: "button", textContent: "ลบ", onclick: () => remove([f.path]) })));
  tr.ondragstart = (e) => {
    if (!selected.has(f.path)) selected = new Set([f.path]);
    dragging = [...selected];
    e.dataTransfer.setData("text/plain", f.name); e.dataTransfer.effectAllowed = "move";
  };
  tr.ondragend = () => { dragging = []; render(); };
  return tr;
}

function rename(f, cell) {
  const input = el("input", { className: "rename", value: f.name });
  cell.replaceChildren(input); input.focus();
  const dot = f.name.lastIndexOf(".");
  input.setSelectionRange(0, dot > 0 ? dot : f.name.length);
  let done = false;
  const finish = (ok) => {
    if (done) return; done = true;
    const to = input.value.trim();
    if (ok && to && to !== f.name) run(() => mutate("/api/admin/move", json({ path: f.path, name: to })));
    else render();
  };
  input.onkeydown = (e) => { if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); };
  input.onblur = () => finish(true);
}

function folderOps(d) {
  const stop = (fn) => (e) => { e.stopPropagation(); fn(); };
  return el("span", { className: "fops" },
    el("button", { className: "link", type: "button", textContent: "เปลี่ยนชื่อ", onclick: stop(() => renameFolder(d)) }),
    el("button", { className: "del", type: "button", textContent: "ลบ", onclick: stop(() => removeFolder(d)) }));
}

function renameFolder(d) {
  const to = prompt("เปลี่ยนชื่อโฟลเดอร์", d);
  if (!to || !to.trim() || to.trim() === d) return;
  run(async () => { const r = await mutate("/api/admin/rename-folder", json({ folder: d, name: to })); if (cwd === d) cwd = r.folder; });
}

function removeFolder(d) {
  const n = files.filter((f) => f.folder === d).length;
  if (!confirm("ลบโฟลเดอร์ " + d + " และไฟล์ทั้งหมดข้างใน (" + n + " ไฟล์) ใช่ไหม?\nย้อนกลับไม่ได้")) return;
  run(() => mutate("/api/admin/delete-folder", json({ folder: d })));
}

let replaceTarget = null;
function replacing(f) { replaceTarget = f; $("repl").click(); }

// delete is optimistic: rows vanish now, the server call waits 6 s so Undo can cancel it
function remove(paths) {
  commit();
  files = files.filter((f) => !paths.includes(f.path));
  paths.forEach((p) => selected.delete(p));
  render();
  pending = { paths, timer: setTimeout(commit, 6000) };
  $("tmsg").textContent = paths.length === 1 ? "ลบ " + paths[0].split("/").at(-1) + " แล้ว" : "ลบ " + paths.length + " ไฟล์แล้ว";
  $("toast").classList.remove("hidden");
}

function commit() {
  if (!pending) return;
  const { paths, timer } = pending;
  clearTimeout(timer); pending = null;
  $("toast").classList.add("hidden");
  run(async () => { for (const path of paths) await mutate("/api/admin/delete", json({ path })); });
}

$("undo").onclick = () => {
  if (!pending) return;
  clearTimeout(pending.timer); pending = null;
  $("toast").classList.add("hidden");
  load().catch((e) => say(e.message, true));
};
// leaving mid-window: send the delete anyway so the file does not come back
window.addEventListener("pagehide", () => pending?.paths.forEach((path) => fetch("/api/admin/delete", { ...json({ path }), keepalive: true })));

function moveMany(paths, folder) {
  const todo = paths.filter((p) => byPath(p)?.folder !== folder);
  todo.forEach((p) => { byPath(p).folder = folder; });
  if (todo.length) render();
  if (todo.length) run(async () => { for (const path of todo) await mutate("/api/admin/move", json({ path, folder })); });
}

function upload(list, folder) {
  const picked = [...list];
  if (!picked.length) return;
  const fd = new FormData();
  picked.forEach((f) => fd.append("files", f));
  fd.append("category", folder); fd.append("downloadable", false);
  say("กำลังอัปโหลด...");
  run(() => mutate("/api/admin/upload", { method: "POST", body: fd }));
}

// folder rows and breadcrumbs take uploads and row moves; the list itself takes uploads into the open folder
function dropTarget(node, folder, movable = true) {
  const to = () => (typeof folder === "function" ? folder() : folder);
  node.addEventListener("dragover", (e) => {
    if (hasFiles(e) || (movable && dragging.length)) { e.preventDefault(); e.stopPropagation(); node.classList.add("over"); }
  });
  node.addEventListener("dragleave", () => node.classList.remove("over"));
  node.addEventListener("drop", (e) => {
    node.classList.remove("over");
    if (hasFiles(e)) { e.preventDefault(); e.stopPropagation(); upload(e.dataTransfer.files, to()); }
    else if (movable && dragging.length) { e.preventDefault(); e.stopPropagation(); moveMany(dragging, to()); }
  });
}

dropTarget($("list"), () => cwd, false);
document.addEventListener("dragover", (e) => e.preventDefault());  // never let the browser open a dropped file
document.addEventListener("drop", (e) => e.preventDefault());

$("pick").onclick = () => $("files").click();
$("files").onchange = (e) => { upload(e.target.files, cwd); e.target.value = ""; };
$("repl").onchange = (e) => {
  const [file] = e.target.files, f = replaceTarget;
  e.target.value = ""; replaceTarget = null;
  if (!file || !f) return;
  const fd = new FormData();
  fd.append("path", f.path); fd.append("file", file);
  say("กำลังอัปโหลดทับ " + f.name + "...");
  run(() => mutate("/api/admin/replace", { method: "POST", body: fd }));
};
$("newdir").onclick = async () => {
  const name = prompt("ชื่อโฟลเดอร์ใหม่");
  if (!name || !name.trim()) return;
  try { cwd = (await call("/api/admin/mkdir", json({ folder: name }))).folder; selected.clear(); await load(); } catch (e) { say(e.message, true); }
};
$("all").onchange = (e) => { visible().forEach((f) => (e.target.checked ? selected.add(f.path) : selected.delete(f.path))); render(); };
$("clear").onclick = () => { selected.clear(); render(); };
$("delsel").onclick = () => remove([...selected]);
$("mvsel").onclick = () => {
  $("dest").replaceChildren(el("option", { value: "", textContent: ROOT_LABEL }), ...folders.map((d) => el("option", { value: d, textContent: d })));
  $("dest").value = cwd;
  $("mv").returnValue = ""; $("mv").showModal();
};
$("mv").addEventListener("close", () => { if ($("mv").returnValue === "ok") moveMany([...selected], $("dest").value); });
$("reindex").onclick = reindex;
window.addEventListener("beforeunload", (e) => { if (stale || busy || pending) e.preventDefault(); });

try { const c = JSON.parse(sessionStorage.getItem(CACHE)); if (c) apply(...c); } catch (_) {}  // show last list while the fresh one loads
load().catch((e) => say(e.message, true));
