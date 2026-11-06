# Two-Screen Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three tool pages (chat, tracking, admin entry) with one login that opens a researcher home (to-do first, chat drawer) or a staff workspace (review inbox first, left menu).

**Architecture:** Front-end restructure only. `/` serves a new `home.html` (the current `track.*` files renamed and reshaped). The old chat page moves to `/chat` unchanged and is embedded in the researcher drawer through an `<iframe>`, so no chat code is duplicated. The tracker API, chat API and admin Basic auth are untouched.

**Tech Stack:** FastAPI, vanilla JS, Thai UI, pytest `TestClient`. Node 26 is installed and is used for one pure-function test.

**Spec:** `docs/superpowers/specs/2026-11-07-two-screen-redesign-design.md`

**Branch:** create `feat/redesign` from `feat/tracking` (the tracking work is not merged to `main` yet).

## Global Constraints

- No new dependency, no framework. Text goes into the DOM through `textContent` (the `h()` helper), never `innerHTML` with API data.
- All 209 existing tests stay green, except the three assertions Task 1 moves from `/` to `/chat` and the one it moves from `/track` to `/`.
- `/admin` and `/api/admin/*` keep HTTP Basic auth. Nothing in the new screens may reach them with the mock cookie.
- Researchers see only their own submissions (API already enforces; do not weaken).
- Layout works at phone width (360 px).
- Update `FRAMEWORK.md`, run `graphify update .`, after the code change.

## Review Focus

Failure modes the spec implies but existing tests do not exercise, most likely first. Each has a test or a manual check in the owning task.

1. Logged-out visit to `/` shows the login card, not a blank page (Task 2 manual check).
2. Researcher with zero submissions sees "ไม่มีงานค้าง" and a working chat button (Task 2 and 4 manual checks).
3. `/chat` stays public and can be framed by the drawer (Task 1 test: no `x-frame-options` header).
4. `/track` redirects to `/` without a loop (Task 1 test).
5. Staff not in charge still see disabled Approve/Return (Task 3 manual check).
6. Mixed-status researcher: a returned document outranks a waiting one in the to-do (Task 2 `todoItems` test).

---

### Task 1: Routes and renamed shell

**Files:**
- Rename: `web/track.html` → `web/home.html`, `web/track.js` → `web/home.js`, `web/track.css` → `web/home.css` (use `git mv`)
- Modify: `web/home.html` (title, asset links), `server.py:146-153` (routes)
- Test: `tests/test_server.py`, `tests/test_tracker_api.py`

**Interfaces:**
- Produces: `GET /` serves `web/home.html`; `GET /chat` serves `web/index.html`; `GET /track` redirects to `/`. Later tasks edit `web/home.js` and `web/home.css`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_server.py` change `test_index_page_served_in_thai` and `test_icons_script_served_and_linked` to request `/chat` instead of `/`, and add:

```python
def test_root_serves_the_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and 'lang="th"' in r.text and "home.js" in r.text


def test_chat_page_is_public_and_frameable(client):
    r = client.get("/chat")
    assert r.status_code == 200 and "app.js" in r.text
    assert "x-frame-options" not in r.headers  # the researcher drawer embeds this page


def test_track_redirects_to_root_without_a_loop(client):
    r = client.get("/track", follow_redirects=False)
    assert r.status_code in (307, 308) and r.headers["location"] == "/"
    assert client.get("/").status_code == 200
```

In `tests/test_tracker_api.py` change `test_track_page_and_assets_served` to fetch `/` and assert `"home.js" in r.text`, and that `/static/home.js` and `/static/home.css` return 200.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server.py tests/test_tracker_api.py -q`
Expected: FAIL on the new and changed tests (`/chat` 404, `home.js` missing).

- [ ] **Step 3: Implement**

`git mv` the three files. In `web/home.html` set `<title>RiSA</title>`, link `/static/home.css` and `/static/home.js`, and change the header link `ไปหน้าแชท` (`href="/"`) to nothing (the page is now the home). In `server.py`: `GET /` returns `FileResponse(WEB / "home.html")`; add `GET /chat` returning `FileResponse(WEB / "index.html")`; `GET /track` returns `RedirectResponse("/")` (import from `fastapi.responses`). In `web/admin.html` change the header link text `ไปหน้าแชท` to `กลับหน้าหลัก` (href stays `/`).

- [ ] **Step 4: Run to verify pass**

Run: `pytest -q`
Expected: all pass (209 existing, with the four moved assertions, plus 3 new).

- [ ] **Step 5: Commit**

```bash
git add -A web server.py tests
git commit -m "refactor: serve the tracking app at /, move chat to /chat"
```

---

### Task 2: Researcher home (layout B)

**Files:**
- Create: `web/todo.js` (pure function, node-testable)
- Modify: `web/home.js` (replace `researcherHome` and `researcherDetail`), `web/home.html` (load `todo.js` before `home.js`), `web/home.css`
- Test: `tests/test_todo_js.py`

**Interfaces:**
- Produces in `web/todo.js`: `todoItems(subs) -> [{kind, sub, doc, note}]` where `subs` is a list of submission detail objects (as returned by `GET /api/track/submissions/{sid}`: `steps`, `current_step`, `uploads`) and `kind` is `"returned"` or `"waiting"`. Order: all `"returned"` first, then `"waiting"`, each in input order. Only the latest upload per `doc_name` for the current step counts; `"returned"` means its status is `returned`, `"waiting"` means `sent`. Also exports via `if (typeof module !== "undefined") module.exports = { todoItems };`.
- Produces in `web/home.js`: `docRow(sub, name, reload)` returning the existing per-document block (status text, AI findings, staff note, upload and send buttons) taken from the current `researcherDetail` code; `researcherHome()` renders: a "สิ่งที่ต้องทำ" card (list from `todoItems`, or "ไม่มีงานค้าง" when empty), then one card per submission with title, type, staff in charge, `stepper(sub)` and the current step's documents through `docRow`.

- [ ] **Step 1: Write the failing test** in `tests/test_todo_js.py`, skipped when `node` is not on PATH. It runs `node -e` that requires `web/todo.js` and checks three cases through `subprocess`:

```python
import json, shutil, subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
JS = Path(__file__).resolve().parent.parent / "web" / "todo.js"


def run(subs):
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).todoItems({json.dumps(subs)})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def sub(sid, uploads, step=0, docs=("Form A",)):
    return {"id": sid, "current_step": step, "steps": [{"title": "S", "documents": list(docs)}], "uploads": uploads}


def up(doc, status, id_=1, step=0, note=""):
    return {"id": id_, "doc_name": doc, "status": status, "step_index": step, "note": note}


def test_empty_when_nothing_pending():
    assert run([sub(1, [up("Form A", "approved")]), sub(2, [])]) == []


def test_returned_comes_before_waiting_across_submissions():
    got = run([sub(1, [up("Form A", "sent")]), sub(2, [up("Form A", "returned", note="fix")])])
    assert [(g["kind"], g["sub"]["id"]) for g in got] == [("returned", 2), ("waiting", 1)]
    assert got[0]["note"] == "fix"


def test_only_latest_upload_per_document_counts():
    got = run([sub(1, [up("Form A", "returned", id_=1), up("Form A", "sent", id_=2)])])
    assert [g["kind"] for g in got] == ["waiting"]
```

Before writing, confirm the upload object field names (`step_index`, `note`, `id`, `doc_name`, `status`) against `Tracker.get_submission` in `tracker.py` and adjust the test fixture to the real keys.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_todo_js.py -q`
Expected: FAIL (cannot find module `web/todo.js`).

- [ ] **Step 3: Implement `todoItems`** in `web/todo.js` to the interface above (latest upload per document wins; later in the `uploads` list or higher `id` is later, match how `Tracker.latest_uploads` decides).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_todo_js.py -q`
Expected: 3 passed.

- [ ] **Step 5: Build the home page in `web/home.js`.** Extract `docRow` from `researcherDetail`; rewrite `researcherHome` as described (fetch `GET /submissions`, then `GET /submissions/{id}` for each in parallel; on any upload or send, call `researcherHome()` again). Delete `researcherDetail`. Add CSS in `web/home.css` for `.todo` rows and card spacing; keep the existing look. No new HTML injection paths.

- [ ] **Step 6: Run the suite and check by hand**

Run: `pytest -q` and `node --check web/home.js`
Expected: all pass, no syntax error.

Manual (run `./run.sh`, open `/`): logged out shows the login card; login as r1 shows the to-do card and submission cards; r2 with no submissions shows "ไม่มีงานค้าง"; at 360 px width nothing overflows horizontally.

- [ ] **Step 7: Commit**

```bash
git add web tests
git commit -m "feat: researcher home with to-do list and inline submission cards"
```

---

### Task 3: Staff workspace (layout A)

**Files:**
- Modify: `web/home.js` (`staffHome` and menu), `web/home.css`, `web/home.html` (page is wrapper only; no change needed if header stays)

**Interfaces:**
- Consumes: existing `staffSubs`, `staffQueue`, `staffTypes`, `staffDetail`, `draftEditor`, `api`, `act`, `show` in `web/home.js`; `GET /api/track/review-queue`.
- Produces: `staffHome()` renders a two-column layout: a left menu with four items in this order and these labels: `📥 รอตรวจ (N)` (N = length of the review queue), `📋 ทุกงาน`, `🧩 ประเภททุน`, `📁 ไฟล์ความรู้`. The state variable `tab` takes `"queue" | "subs" | "types"`, default `"queue"`. `📁 ไฟล์ความรู้` is a link to `/admin` that opens in a new tab and is not a tab. Each review-queue row shows, in its header line, the submission title, the document name and the AI finding count ("AI พบ N ข้อ" or "AI ไม่พบปัญหา"; "AI ตรวจไม่ได้" for `cannot_check`), above the existing review controls (findings checkboxes, note, Approve, Return, "เปิดไฟล์"). Navigating away from `staffDetail` or `draftEditor` returns to `staffHome()` on the last chosen tab.

- [ ] **Step 1: Restructure `staffHome`** to the interface above. Fetch the queue once per render for the count and pass it to `staffQueue` to avoid a second request. Do not change any API call or the review and move logic.

- [ ] **Step 2: CSS.** Two columns at desktop width (menu about 200 px). Below 700 px the menu becomes a horizontal row above the content.

- [ ] **Step 3: Run the suite**

Run: `pytest -q` and `node --check web/home.js`
Expected: all pass.

Manual: login as s1; the page opens on รอตรวจ with the correct count; upload as r1 and send a document to see the count change; menu items switch content; `📁 ไฟล์ความรู้` asks for the Basic-auth password; login as s2 on s1's submission shows Approve and Return disabled; at 360 px the menu is a row.

- [ ] **Step 4: Commit**

```bash
git add web
git commit -m "feat: staff workspace with review inbox first and left menu"
```

---

### Task 4: Chat drawer for researchers

**Files:**
- Modify: `web/home.js`, `web/home.css`

**Interfaces:**
- Produces: `chatDrawer()` in `web/home.js`, called once by `start()` for researchers only (not staff, not logged out). It appends a fixed 💬 button (bottom right, label "ถาม AI") and a panel that slides in from the right (full width on phones, about 420 px on desktop) containing a header with a close button and an `<iframe src="/chat">`. The iframe `src` is set the first time the drawer opens, not at page load. `Escape` closes the drawer. Logging out removes the button and panel.

- [ ] **Step 1: Implement `chatDrawer` and its CSS.** Use `h()` for all nodes. The iframe needs a `title` attribute ("แชทผู้ช่วย RiSA") for accessibility. Respect `prefers-reduced-motion` (no slide animation).

- [ ] **Step 2: Run the suite**

Run: `pytest -q` and `node --check web/home.js`
Expected: all pass.

Manual: as r1 the button appears, opens the chat, a question gets an answer, the history survives closing and reopening the drawer, `Escape` closes it; as s1 and when logged out no button appears; at 360 px the drawer fills the screen and the close button is reachable.

- [ ] **Step 3: Commit**

```bash
git add web
git commit -m "feat: chat drawer on the researcher home"
```

---

### Task 5: Docs and graph

**Files:**
- Modify: `FRAMEWORK.md`

- [ ] **Step 1:** Update `FRAMEWORK.md`: new routes (`/`, `/chat`, `/track` redirect, `/admin` unchanged), the researcher home and staff workspace, the drawer reusing `/chat`, `todo.js`, file renames, and the new test count from the last `pytest` run.
- [ ] **Step 2:** Run `pytest -q` (all green, record the count) and `graphify update .`.
- [ ] **Step 3: Commit**

```bash
git add FRAMEWORK.md graphify-out
git commit -m "docs: framework notes for the two-screen redesign"
```

Do not merge or push without the user's word.
