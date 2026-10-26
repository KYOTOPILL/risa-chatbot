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
