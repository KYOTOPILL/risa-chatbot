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
if (typeof module !== "undefined") module.exports = { todoItems };
