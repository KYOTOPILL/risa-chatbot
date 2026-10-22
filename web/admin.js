const $ = (id) => document.getElementById(id);
const msg = $("msg"), filesIn = $("files");

function say(text, err = false) { msg.textContent = text; msg.className = "status" + (err ? " err" : ""); }
const kb = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

async function call(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "เกิดข้อผิดพลาด (" + res.status + ")");
  return data;
}

async function refresh() {
  const rows = await call("/api/admin/files");
  const body = $("rows");
  body.replaceChildren();
  for (const r of rows) {
    const tr = document.createElement("tr");
    const cells = [r.path, r.category, r.downloadable ? "ได้" : "-", kb(r.size), r.mtime];
    cells.forEach((t, i) => {
      const td = document.createElement("td");
      if (i === 1) { const b = document.createElement("span"); b.className = "badge"; b.textContent = t; td.append(b); }
      else td.textContent = t;
      tr.append(td);
    });
    const td = document.createElement("td");
    const del = document.createElement("button");
    del.className = "del"; del.type = "button"; del.textContent = "ลบ";
    del.onclick = () => remove(r.path);
    td.append(del); tr.append(td);
    if (!r.supported) tr.title = "ชนิดไฟล์นี้ระบบไม่อ่าน";
    body.append(tr);
  }
  $("count").textContent = "(" + rows.length + ")";
  $("empty").classList.toggle("hidden", rows.length > 0);
  const cats = [...new Set(rows.map((r) => r.category))];
  $("cats").replaceChildren(...cats.map((c) => Object.assign(document.createElement("option"), { value: c })));
}

async function reindex() {
  say("กำลังอัปเดตดัชนี... (แชทจะรอสักครู่)");
  const r = await call("/api/admin/reindex", { method: "POST" });
  const skipped = r.skipped.length ? " · ข้าม " + r.skipped.length + " ไฟล์: " + r.skipped.join(", ") : "";
  say("อัปเดตดัชนีแล้ว " + r.indexed + " ไฟล์" + skipped, r.skipped.length > 0);
}

async function guarded(fn, buttons) {
  buttons.forEach((b) => (b.disabled = true));
  try { await fn(); } catch (e) { say(e.message, true); } finally { buttons.forEach((b) => (b.disabled = false)); }
}

$("up").addEventListener("submit", (e) => {
  e.preventDefault();
  if (!filesIn.files.length) return say("กรุณาเลือกไฟล์ก่อน", true);
  guarded(async () => {
    const fd = new FormData();
    [...filesIn.files].forEach((f) => fd.append("files", f));
    fd.append("category", $("category").value);
    fd.append("downloadable", $("dl").checked);
    say("กำลังอัปโหลด...");
    const r = await call("/api/admin/upload", { method: "POST", body: fd });
    filesIn.value = ""; $("picked").textContent = "อัปโหลดแล้ว " + r.saved.length + " ไฟล์";
    await reindex(); await refresh();
  }, [$("go"), $("reindex")]);
});

function remove(path) {
  if (!confirm("ลบไฟล์นี้ใช่ไหม?\n" + path)) return;
  guarded(async () => { await call("/api/admin/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }); await reindex(); await refresh(); }, [$("reindex")]);
}

$("reindex").addEventListener("click", () => guarded(async () => { await reindex(); await refresh(); }, [$("reindex"), $("go")]));
filesIn.addEventListener("change", () => { $("picked").textContent = filesIn.files.length ? filesIn.files.length + " ไฟล์ที่เลือก" : "ลากไฟล์มาวาง หรือคลิกเพื่อเลือก (PDF, DOCX, TXT, MD)"; });
const drop = $("drop");
["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => { e.preventDefault(); filesIn.files = e.dataTransfer.files; filesIn.dispatchEvent(new Event("change")); });

refresh().catch((e) => say(e.message, true));
