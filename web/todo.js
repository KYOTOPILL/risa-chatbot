// To-do list for a researcher, most urgent first: documents staff sent back, documents ready to send, documents not filled in yet (or saved as a draft),
// then documents waiting for staff. Looks at the documents of each request's current step. Pure, so node can test it.
const TODO_ORDER = ["returned", "send", "fill", "waiting"];
const TODO_KIND = { returned: "returned", screened: "send", cannot_check: "send", draft: "fill", sent: "waiting" };
function todoItems(subs) {
  const out = Object.fromEntries(TODO_ORDER.map((k) => [k, []]));
  for (const sub of subs) {
    const latest = new Map();  // later id wins, the API already sends only the newest, this guards a stale list
    for (const u of sub.uploads) if (!latest.has(u.doc_name) || latest.get(u.doc_name).id < u.id) latest.set(u.doc_name, u);
    const docs = sub.steps[sub.current_step]?.documents || [];  // past the last step: none
    for (const doc of docs) {
      const u = latest.get(doc), kind = u ? TODO_KIND[u.status] : "fill";
      if (kind) out[kind].push({ kind, sub, doc, note: u?.note || "", draft: u?.status === "draft" });
    }
  }
  return TODO_ORDER.flatMap((k) => out[k]);
}

// SQLite stores UTC as "YYYY-MM-DD HH:MM:SS"
const utc = (ts) => new Date(ts.replace(" ", "T") + "Z");
const DAY = 86400000;

// Staff numbers: documents waiting, submissions still open, documents that have waited over 7 days (from upload time).
function staffStats(queue, subs, now) {
  const t = new Date(now).getTime();
  return {
    waiting: queue.length,
    active: subs.filter((s) => s.current_step < s.step_count).length,
    old: queue.filter((u) => t - utc(u.created).getTime() > 7 * DAY).length,
  };
}

function agoText(ts, now) {
  const ms = new Date(now).getTime() - utc(ts).getTime();
  if (ms < 3600000) return "เมื่อสักครู่";
  if (ms < DAY) return Math.floor(ms / 3600000) + " ชั่วโมงก่อน";
  const d = Math.floor(ms / DAY);
  return d === 1 ? "เมื่อวาน" : d + " วันก่อน";
}
if (typeof module !== "undefined") module.exports = { todoItems, staffStats, agoText };
