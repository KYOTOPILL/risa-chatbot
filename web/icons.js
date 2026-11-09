// File-type icon shown after a file link name: a page with a folded corner and a coloured label.
// Edit TYPES for labels and COLORS for colours.
const TYPES = { pdf: "pdf", doc: "doc", docx: "doc", xls: "xls", xlsx: "xls", csv: "xls", ppt: "ppt", pptx: "ppt", txt: "txt", md: "txt" };
const COLORS = { pdf: "#d92d20", doc: "#2563eb", xls: "#16a34a", ppt: "#ea580c", txt: "#64748b", other: "#6b7777" };

function fileIcon(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const type = TYPES[ext] || "other";
  const color = COLORS[type];
  const label = (TYPES[ext] || ext).slice(0, 4).toUpperCase();
  const el = document.createElement("span");
  el.className = "ftype";
  el.setAttribute("aria-hidden", "true");
  el.innerHTML =
    `<svg viewBox="0 0 20 24" width="20" height="24">` +
    `<path d="M3 1h9l6 6v15a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1z" fill="#fff" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>` +
    `<path d="M12 1v6h6" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>` +
    `<rect x="2" y="12.5" width="16" height="8.5" rx="1" fill="${color}"/>` +
    `<text x="10" y="19" text-anchor="middle" font-family="Arial,sans-serif" font-size="${label.length > 3 ? 5.5 : 6.5}" font-weight="700" fill="#fff">${label}</text>` +
    `</svg>`;
  return el;
}

// UI icons: one stroke width and one grid for the whole set. icon("queue") returns an <svg> that takes the text colour.
const ICONS = {
  queue: "M3 13h5l1 3h6l1-3h5M5 5h14l2 8v6H3v-6z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  types: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  folder: "M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  chat: "M4 5h16v11H9l-5 4z",
  check: "m5 12 5 5 9-10",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14a6.5 6.5 0 0 1 3.5 6",
  form: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
};
function icon(name) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), p = document.createElementNS(ns, "path");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
  p.setAttribute("d", ICONS[name]); svg.append(p);
  return svg;
}
