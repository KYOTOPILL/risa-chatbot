"""Fill tracker.db with fake people so the ผู้ใช้ tab can be tried with a long list. Safe to run again (nobody is added twice).
Usage: .venv/bin/python scripts/seed_demo_users.py [staff email ...]
All fake researchers use emails like demo.nida01@cmu.ac.th, so they are easy to find and disable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import TRACKER_DB  # noqa: E402
from app.features.tracker import Tracker  # noqa: E402

STAFF = sys.argv[1:] or ["pawarit_di@cmu.ac.th"]
NAMES = ["Nida", "Somchai", "Malee", "Anan", "Preecha", "Kanya", "Wichai", "Suda", "Thanat", "Pim", "Arthit", "Naree", "Korn", "Jira", "Boon",
         "Mali", "Chai", "Orn", "Tawan", "Ploy", "Sak", "Duang", "Ek", "Fah", "Gun", "Hana", "Ice", "Jane", "Kit", "Lek", "Mint", "Nok", "Oat", "Pat", "Rin", "Sai", "Tan", "Udom", "Vee", "Wan"]
SURNAMES = ["Suksai", "Jaidee", "Rungrot", "Thongdee", "Srisuk"]

tk = Tracker(TRACKER_DB)
print("staff:", tk.add_users(STAFF, "staff"))
emails = [f"demo.{n.lower()}{i + 1:02d}@cmu.ac.th" for i, n in enumerate(NAMES)]
print("researchers:", {k: len(v) for k, v in tk.add_users(emails, "researcher").items()})
for i, (n, e) in enumerate(zip(NAMES, emails)):
    if i < 28:  # most have logged in once: the real CMU name replaces the placeholder
        tk.login_user(e, f"{n} {SURNAMES[i % len(SURNAMES)]}")
    if i in (37, 39):  # two who lost access
        tk.set_active(e, False)
print("now:", tk.page_users()["counts"])
