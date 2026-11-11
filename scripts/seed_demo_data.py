"""Fill tracker.db with demo work so every screen has something to show: request types (open, pinned, limited, draft, closed), requests in every
state, uploaded documents with AI findings, a staff review queue, notifications and profiles. Safe to run again: a type or request that already
exists (same name or title) is skipped.
Usage: .venv/bin/python scripts/seed_demo_data.py
Log in as the demo researchers (somchai, nida) or staff (malee, anan) to see each side; the real staff email (pawarit_di@cmu.ac.th) also owns a few requests.
Files are tiny placeholders in uploads/demo/."""
import base64
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import docx  # noqa: E402

from app.core.config import TRACKER_DB, UPLOAD_DIR  # noqa: E402
from app.features.tracker import Tracker  # noqa: E402

tk = Tracker(TRACKER_DB)
OUT = UPLOAD_DIR / "demo"
OUT.mkdir(parents=True, exist_ok=True)
STAFF = [u["id"] for u in tk.list_users() if u["role"] == "staff" and u["active"]]  # roles may have been changed in the UI, so ask the table
assert STAFF, "no active staff: set RISA_STAFF_EMAILS first"
S1, S2 = STAFF[0], STAFF[-1]
DEMO = [f"demo.{n}@cmu.ac.th" for n in ("nida01", "somchai02", "malee03", "anan04", "preecha05", "kanya06", "wichai07", "suda08")]
tk.add_users(DEMO, "researcher")  # a no-op for the ones seed_demo_users.py already made


# ---------- tiny real files, so staff can open what a researcher "uploaded" ----------
def pdf(text: str) -> bytes:
    body = f"BT /F1 16 Tf 60 760 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)


def png() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + b"\xcc\xdd\xee" * 8 for _ in range(8)))) + chunk(b"IEND", b"")


def make_file(sid: int, doc: str, fmts: list[str]) -> tuple[str, str]:
    kind = "pdf" if "pdf" in fmts else "docx" if "docx" in fmts else "png"
    name = f"{doc}.{kind}"
    path = OUT / f"{sid}_{abs(hash(doc)) % 10**6}.{kind}"
    if kind == "pdf":
        path.write_bytes(pdf("Demo document"))
    elif kind == "png":
        path.write_bytes(png())
    else:
        d = docx.Document()
        d.add_heading(doc, 1)
        d.add_paragraph("เอกสารตัวอย่างสำหรับทดสอบระบบ ไม่ใช่ข้อมูลจริง")
        d.save(path)
    return name, str(path)


# ---------- types ----------
def category(name: str) -> int:
    return next((c["id"] for c in tk.list_categories() if c["name"] == name), None) or tk.add_category(name)


def step(title, docs=(), **formats):
    return {"title": title, "documents": list(docs), "page": None, "unsure": False, **({"formats": {k.replace("_", " "): v for k, v in formats.items()}} if formats else {})}


def make_type(name, steps, cat=None, pin=False, owner=None, audience=None, approved=True, open_=True):
    with tk._db() as db:
        row = db.execute("SELECT v.id, v.type_id FROM versions v JOIN types t ON t.id = v.type_id WHERE t.name = ? ORDER BY v.id DESC", (name,)).fetchone()
    if row:
        return row["id"]
    vid = tk.create_type(name, steps, "")
    tid = tk.get_version(vid)["type_id"]
    if cat:
        tk.set_type_category(tid, category(cat))
    if approved:
        tk.approve(vid)
        if open_:
            tk.set_type_open(tid, True, owner)
        if pin:
            tk.set_type_pinned(tid, True)
        if audience:
            tk.set_type_audience(tid, audience)
    return vid


GRANT = make_type("ทุนวิจัยภายใน CMU", [
    step("ยื่นใบสมัครทุน", ["ใบสมัครขอรับทุน", "โครงร่างงานวิจัย", "สำเนาบัตรประชาชน"], **{"สำเนาบัตรประชาชน": ["pdf", "image"]}),
    step("พิจารณาโดยคณะกรรมการ"), step("ทำสัญญารับทุน", ["สัญญารับทุน"]), step("เบิกจ่ายงวดแรก", ["ใบเบิกเงินงวดที่ 1"])],
    cat="ทุนวิจัย", pin=True, owner=S1)
TRAVEL = make_type("ขอเบิกค่าเดินทางไปประชุมวิชาการ", [
    step("ส่งใบเบิก", ["แบบฟอร์มขอเบิก", "ใบเสร็จรับเงิน", "หนังสืออนุมัติเดินทาง"], **{"ใบเสร็จรับเงิน": ["pdf", "image"]}),
    step("การเงินตรวจสอบ"), step("โอนเงินเข้าบัญชี")],
    cat="การเงินและเบิกจ่าย", owner=S2)
ETHICS = make_type("ขอรับรองจริยธรรมการวิจัยในมนุษย์", [
    step("ส่งเอกสารโครงการ", ["แบบฟอร์ม IRB-1", "โครงร่างงานวิจัย", "ใบยินยอมผู้เข้าร่วมวิจัย"]),
    step("คณะกรรมการพิจารณา"), step("ออกใบรับรอง")],
    cat="จริยธรรมการวิจัย", owner=S1, audience=["r1", DEMO[0], DEMO[1]])  # limited: r2 does not see it
make_type("ขอใช้ห้องประชุมและอุปกรณ์", [step("ส่งคำขอ", ["แบบฟอร์มขอใช้ห้อง"])], approved=False)  # a draft
make_type("ทุนโครงการ Startup ประจำปี 2568", [step("ส่งข้อเสนอโครงการ", ["ข้อเสนอโครงการ", "แผนธุรกิจ"]), step("นำเสนอต่อคณะกรรมการ")],
          cat="ทุนวิจัย", open_=False)  # approved, but closed to new requests

FINDINGS = [
    {"kind": "missing", "text": "ยังไม่ได้ระบุงบประมาณรวมของโครงการ", "field": "งบประมาณ", "fix": "เพิ่มตารางงบประมาณพร้อมยอดรวม"},
    {"kind": "unclear", "text": "กรอบเวลาดำเนินงานไม่ชัดเจน", "field": "ระยะเวลา", "fix": "ระบุวันเริ่มและวันสิ้นสุดโครงการ"},
    {"kind": "incorrect", "text": "ยอดรวมในตารางไม่ตรงกับผลรวมรายการ", "field": "ยอดรวม", "fix": "ตรวจสอบการคำนวณอีกครั้ง"},
]


# ---------- requests ----------
def request(title, vid, who, staff, docs, advance_to=None):
    """docs: {step_index: {doc: state}}; state is draft, screened, sent, approved, returned or returned:<note>. Approving the last document of a step advances it."""
    with tk._db() as db:
        if db.execute("SELECT 1 FROM submissions WHERE title = ?", (title,)).fetchone():
            return
    sid = tk.create_submission(title, vid, [who], staff, staff)
    steps = tk.get_version(vid)["steps"]
    for si, states in docs.items():
        if tk.get_submission(sid, staff, "staff")["current_step"] < si:
            tk.move_step(sid, staff, si, "ผ่านขั้นตอนก่อนหน้า")
        for doc, state in states.items():
            name, path = make_file(sid, doc, (steps[si].get("formats") or {}).get(doc, ["pdf", "docx"]))
            base, _, note = state.partition(":")
            found = FINDINGS[:2] if base in ("screened", "sent") and doc == "โครงร่างงานวิจัย" else []
            uid = tk.add_upload(sid, si, doc, name, path, found, "draft" if base == "draft" else "screened")
            if base in ("sent", "approved", "returned"):
                tk.send_upload(uid, who)
            if base == "approved":
                tk.review_upload(uid, staff, "approve", [], "")
            elif base == "returned":
                tk.review_upload(uid, staff, "return", [], note or "กรุณาตรวจสอบและแก้ไขตามข้อเสนอแนะ แล้วส่งใหม่")
    if advance_to is not None:
        tk.move_step(sid, staff, advance_to, "ตรวจสอบเรียบร้อย")


nm = {u: tk.name_of(u) for u in ["r1", "r2", *DEMO]}
A, B, C = "ทุนวิจัยภายใน CMU", "เบิกค่าเดินทาง", "ขอรับรองจริยธรรม"
# researcher view: Somchai has work in every kind of state
request(f"{A} - {nm['r1']}", GRANT, "r1", S1, {0: {"ใบสมัครขอรับทุน": "sent", "โครงร่างงานวิจัย": "screened", "สำเนาบัตรประชาชน": "draft"}})
request(f"{B} (ประชุม ICML) - {nm['r1']}", TRAVEL, "r1", S2, {0: {"แบบฟอร์มขอเบิก": "approved", "ใบเสร็จรับเงิน": "approved", "หนังสืออนุมัติเดินทาง": "approved"}})
request(f"{C} - {nm['r1']}", ETHICS, "r1", S1, {0: {"แบบฟอร์ม IRB-1": "returned:กรุณาระบุจำนวนกลุ่มตัวอย่างให้ชัดเจน", "โครงร่างงานวิจัย": "approved", "ใบยินยอมผู้เข้าร่วมวิจัย": "screened"}})
# Nida: one waiting on the contract step, one finished
request(f"{A} - {nm['r2']}", GRANT, "r2", S2, {0: {"ใบสมัครขอรับทุน": "approved", "โครงร่างงานวิจัย": "approved", "สำเนาบัตรประชาชน": "approved"}, 2: {"สัญญารับทุน": "sent"}})
request(f"{B} (ประชุมที่เชียงใหม่) - {nm['r2']}", TRAVEL, "r2", S1, {0: {"แบบฟอร์มขอเบิก": "approved", "ใบเสร็จรับเงิน": "approved", "หนังสืออนุมัติเดินทาง": "approved"}}, advance_to=3)
# staff view: more people, spread over the staff, so the queue and the list have volume
spread = [(DEMO[0], GRANT, A, {0: {"ใบสมัครขอรับทุน": "sent", "โครงร่างงานวิจัย": "sent", "สำเนาบัตรประชาชน": "sent"}}),
          (DEMO[1], TRAVEL, B, {0: {"แบบฟอร์มขอเบิก": "sent", "ใบเสร็จรับเงิน": "screened", "หนังสืออนุมัติเดินทาง": "draft"}}),
          (DEMO[2], ETHICS, C, {0: {"แบบฟอร์ม IRB-1": "approved", "โครงร่างงานวิจัย": "approved", "ใบยินยอมผู้เข้าร่วมวิจัย": "approved"}}),
          (DEMO[3], GRANT, A, {0: {"ใบสมัครขอรับทุน": "returned", "โครงร่างงานวิจัย": "approved", "สำเนาบัตรประชาชน": "approved"}}),
          (DEMO[4], TRAVEL, B, {0: {"แบบฟอร์มขอเบิก": "approved", "ใบเสร็จรับเงิน": "approved", "หนังสืออนุมัติเดินทาง": "approved"}, 1: {}}),
          (DEMO[5], GRANT, A, {0: {"ใบสมัครขอรับทุน": "approved", "โครงร่างงานวิจัย": "approved", "สำเนาบัตรประชาชน": "approved"}, 2: {"สัญญารับทุน": "approved"}, 3: {"ใบเบิกเงินงวดที่ 1": "sent"}}),
          (DEMO[6], ETHICS, C, {0: {"แบบฟอร์ม IRB-1": "draft"}}),
          (DEMO[7], TRAVEL, B, {0: {"แบบฟอร์มขอเบิก": "approved", "ใบเสร็จรับเงิน": "approved", "หนังสืออนุมัติเดินทาง": "approved"}})]
for i, (who, vid, short, docs) in enumerate(spread):
    request(f"{short} - {nm[who]}", vid, who, STAFF[i % len(STAFF)], docs, advance_to=3 if i == 7 else None)

# ---------- profiles ----------
for uid, phone, fac, color in [("r1", "081-234-5678", "คณะวิทยาศาสตร์", "#2563eb"), ("r2", "089-765-4321", "คณะวิศวกรรมศาสตร์", "#7c3aed"),
                               ("s1", "053-943-001", "ศูนย์บริหารงานวิจัย (RiSA)", "#be123c"), ("s2", "053-943-002", "ศูนย์บริหารงานวิจัย (RiSA)", "#b45309")]:
    tk.set_profile(uid, tk.name_of(uid), phone, fac, color)

with tk._db() as db:
    print({t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("types", "submissions", "uploads", "notifications")}, "| review queue:", len(tk.review_queue()))
