// To-do list for a researcher: documents staff sent back, then documents waiting for staff. Pure, so node can test it.
function todoItems(subs) {
  const out = { returned: [], waiting: [] };
  for (const sub of subs) {
    const latest = new Map();  // later id wins, the API already sends only the newest, this guards a stale list
    for (const u of sub.uploads) if (!latest.has(u.doc_name) || latest.get(u.doc_name).id < u.id) latest.set(u.doc_name, u);
    for (const u of latest.values()) {
      const kind = u.status === "returned" ? "returned" : u.status === "sent" ? "waiting" : null;
      if (kind) out[kind].push({ kind, sub, doc: u.doc_name, note: u.note || "" });
    }
  }
  return [...out.returned, ...out.waiting];
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
