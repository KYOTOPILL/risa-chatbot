# Tracking and Document Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a researcher/staff dashboard to the RiSA app: per-submission step tracking, AI-drafted step lists per submission type, and a two-stage (AI, then staff) document check.

**Architecture:** One new SQLite-backed module `tracker.py` holds all rules (visibility, who may move a step, version pinning, when Approve advances). `steps_ai.py` holds the two LLM calls (draft steps, screen document) behind an injectable `llm` argument, like `rag.answer`. `tracker_api.py` is a FastAPI router mounted in `server.py`, with a mock cookie login. A static front end in `web/track.*` follows the existing `web/admin.*` style, in Thai.

**Tech Stack:** Python, FastAPI, stdlib `sqlite3`, existing `rag.chat`, `extract.py`, pytest with `TestClient`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-06-tracking-and-document-check-design.md`. Mockups: `.superpowers/brainstorm/45921-1793946993/content/*.html`.

## Global Constraints

- No new dependencies; no new framework. Match `admin.py` style (module docstring, small functions, `ponytail:` comments for known ceilings).
- Researchers see only submissions they belong to. Staff see all submissions. Only the staff in charge may change a submission.
- Staff create submissions. Several researchers may share one.
- AI-drafted steps are never live until staff approve. AI never moves a step.
- A submission pins the type version it started with. Editing a type creates a new draft version and never changes in-flight submissions.
- Uploads: `.pdf` and `.docx` only, max 10 MB (`10 * 1024 * 1024`). Scanned PDF with no text layer: status `cannot_check`, researcher may still send.
- Researcher may always send a document to staff, whatever the AI found.
- A step may need several documents, each uploaded and checked separately. Approve advances the submission only when every document of the current step has an approved latest upload.
- Mock login: fixed `MOCK_USERS` in `config.py`, plain `uid` cookie. Real CMU login replaces only the `current_user` dependency.
- Data files `tracker.db` and `uploads/` are git-ignored. Never commit real researcher documents.
- UI text is Thai (matches `web/admin.html`). The mockups were English; this is a builder call.
- Update `FRAMEWORK.md` whenever a function or behaviour is added (project memory rule), and run `graphify update .` after code changes (project `CLAUDE.md`).

## Review Focus

- Researcher requests a submission id that is not theirs: 404, same as a missing id (no leak that it exists).
- Scanned or empty PDF: `cannot_check`, upload still sendable, nothing crashes.
- LLM returns non-JSON or wrong shape: step draft returns an error and saves nothing; screening becomes `cannot_check`.
- Hostile upload: `../../x.pdf` filename, `.exe`, 11 MB file: rejected or sanitized, nothing written outside `uploads/`.
- Step list edited while a submission is in flight; `move_step` target out of range or by a non-owner staff.

---

## File Structure

- Create `tracker.py`: `Tracker` class, SQLite schema, all rules. No FastAPI, no LLM.
- Create `steps_ai.py`: `draft_steps`, `screen_document`, `find_template`. LLM injected.
- Create `tracker_api.py`: router, mock login, role dependencies, upload handling.
- Create `web/track.html`, `web/track.js`, `web/track.css`: login, researcher stepper, staff screens.
- Modify `config.py`: `MOCK_USERS`, `UPLOAD_DIR`, `TRACKER_DB`, `MAX_UPLOAD_BYTES`.
- Modify `extract.py`: add `extract_pages`.
- Modify `server.py`: include router, serve `/track`.
- Modify `.gitignore`, `FRAMEWORK.md`.
- Tests: `tests/test_tracker.py`, `tests/test_steps_ai.py`, `tests/test_tracker_api.py`.

---

### Task 1: Types and versions in `tracker.py`

**Files:**
- Create: `tracker.py`, `tests/test_tracker.py`
- Modify: `config.py`

**Interfaces:**
- Produces:
  - `config.py`: `MOCK_USERS: dict[str, dict]` e.g. `{"r1": {"name": "Somchai", "role": "researcher"}, "r2": ..., "s1": {"name": "Malee", "role": "staff"}, "s2": ...}`; `TRACKER_DB = ROOT / "tracker.db"`; `UPLOAD_DIR = ROOT / "uploads"`; `MAX_UPLOAD_BYTES = 10 * 1024 * 1024`.
  - `Step = dict` with keys `title: str`, `documents: list[str]`, `page: int | None`, `unsure: bool`.
  - `Tracker(path: Path)`; creates tables on init.
  - `create_type(name: str, steps: list[Step], source_file: str) -> int` returns a draft `version_id`.
  - `new_version(type_id: int, steps: list[Step], source_file: str) -> int` draft version number n+1 for an existing type.
  - `update_draft(version_id: int, steps: list[Step]) -> None`; raises `ValueError` if version is not a draft.
  - `approve(version_id: int) -> None`.
  - `get_version(version_id: int) -> dict | None` keys `id, type_id, type_name, version, status ("draft"|"approved"), steps, source_file`.
  - `list_types() -> list[dict]` newest approved version per type, same keys as `get_version`.

- [ ] **Step 1: Write failing tests** in `tests/test_tracker.py` (fixture `tk(tmp_path)` returns `Tracker(tmp_path / "t.db")`):
  - `test_new_type_is_a_draft_and_not_listed`: after `create_type`, `get_version(v)["status"] == "draft"` and `list_types() == []`.
  - `test_approve_lists_the_type`: after `approve(v)`, `[t["id"] for t in list_types()] == [v]`.
  - `test_update_draft_rejected_after_approval`: `pytest.raises(ValueError)`.
  - `test_new_version_does_not_replace_approved_until_approved`: v1 approved, `new_version` makes v2 draft, `list_types()` still returns v1; after `approve(v2)` returns v2 with `version == 2`.
- [ ] **Step 2: Run** `pytest tests/test_tracker.py -v`. Expected: FAIL, `ModuleNotFoundError: tracker`.
- [ ] **Step 3: Implement** `Tracker` in `tracker.py` with stdlib `sqlite3` (`row_factory`, steps stored as JSON text, one connection per call so threads are safe) and add the `config.py` values.
- [ ] **Step 4: Run** the same command. Expected: all PASS.
- [ ] **Step 5: Commit** `git add tracker.py config.py tests/test_tracker.py && git commit -m "feat: tracker types with draft/approved versions"`

### Task 2: Submissions, visibility, step moves

**Files:** Modify `tracker.py`, `tests/test_tracker.py`

**Interfaces:**
- Consumes: Task 1 `Tracker`, `approve`.
- Produces on `Tracker`:
  - `create_submission(title: str, version_id: int, researcher_ids: list[str], staff_id: str) -> int`; `ValueError` if version not approved or `researcher_ids` empty. `current_step` starts at `0`.
  - `list_submissions(user_id: str, role: str) -> list[dict]` staff: all; researcher: only where listed. Dict keys `id, title, type_name, staff_id, researcher_ids, current_step, step_count`.
  - `get_submission(sid: int, user_id: str, role: str) -> dict | None`; `None` when not visible or missing. Adds `steps` (from the pinned version) and `events` (list of `{from_step, to_step, staff_id, at, note}`).
  - `move_step(sid: int, staff_id: str, to_step: int, note: str = "") -> None`; `PermissionError` if `staff_id` is not in charge; `ValueError` unless `0 <= to_step <= step_count` (`step_count` means completed). Writes one event row.

- [ ] **Step 1: Write failing tests:**
  - `test_researcher_sees_only_own`: r1 and r2 each in their own submission; `list_submissions("r1","researcher")` has one item.
  - `test_shared_submission_visible_to_all_its_researchers`.
  - `test_other_researchers_submission_is_none`: `get_submission(sid,"r2","researcher") is None`.
  - `test_staff_sees_all_but_only_in_charge_moves`: `list_submissions("s2","staff")` has all; `move_step(sid,"s2",1)` raises `PermissionError`; `move_step(sid,"s1",1)` works, `current_step == 1`, one event.
  - `test_move_step_bounds_and_backward`: `to_step=-1` and `step_count+1` raise `ValueError`; moving back from 2 to 1 works and logs both events.
  - `test_in_flight_submission_keeps_its_version`: after `new_version`+`update_draft`+`approve` of v2, `get_submission(...)["steps"]` is still v1's.
- [ ] **Step 2: Run** `pytest tests/test_tracker.py -v`. Expected: FAIL, `AttributeError`.
- [ ] **Step 3: Implement** the methods. Visibility is enforced inside `Tracker`, not in the router, so every caller gets it.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: submissions with visibility and step moves"`

### Task 3: Mock login and router skeleton

**Files:**
- Create: `tracker_api.py`, `tests/test_tracker_api.py`
- Modify: `server.py` (`app.include_router(tracker_api.router)`), `state.py` (add `get_tracker()` returning a lazily built `Tracker(TRACKER_DB)`, same pattern as `get_store`)

**Interfaces:**
- Consumes: Task 2 `Tracker`.
- Produces:
  - `router = APIRouter(prefix="/api/track")`.
  - `POST /api/track/login` body `{"user_id": str}` sets cookie `uid`, returns `{"id","name","role"}`; 401 for an id not in `MOCK_USERS`.
  - `POST /api/track/logout`; `GET /api/track/me` returns the user or 401.
  - `current_user(request) -> User` dependency (`User = dataclass(id, name, role)`); `require_staff` dependency (403 for researchers).
  - `GET /api/track/submissions`, `GET /api/track/submissions/{sid}` (404 when `get_submission` is `None`).
  - `POST /api/track/submissions` (staff) body `{title, version_id, researcher_ids, staff_id}`.
  - `POST /api/track/submissions/{sid}/move` (staff) body `{to_step, note}`; 403 on `PermissionError`, 400 on `ValueError`.
- Test fixture: `state.get_tracker` monkeypatched to a tmp `Tracker`, as `tests/test_admin.py` patches `state.get_store`.

- [ ] **Step 1: Write failing tests:**
  - `test_login_unknown_user_401`, `test_login_sets_cookie_and_me_returns_role`.
  - `test_anonymous_requests_401` for `/submissions` and `/me`.
  - `test_researcher_cannot_create_or_move` (403).
  - `test_researcher_gets_404_for_foreign_submission`: r2 requests r1's id, status `404`.
  - `test_staff_not_in_charge_move_403`; `test_move_out_of_range_400`.
- [ ] **Step 2: Run** `pytest tests/test_tracker_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** router and wire it. `# ponytail: plain uid cookie, anyone can forge it; replaced by CMU login before real use` on `current_user`.
- [ ] **Step 4: Run** `pytest tests -q`. Expected: all PASS, existing tests untouched.
- [ ] **Step 5: Commit** `git commit -am "feat: mock login and submissions API"`

### Task 4: AI step drafting

**Files:**
- Create: `steps_ai.py`, `tests/test_steps_ai.py`
- Modify: `extract.py` (add `extract_pages(path: Path) -> list[str]`: one string per PDF page via the same `pymupdf` + `clean_thai` path; non-PDF returns `[extract_text(path)]`), `tracker_api.py`

**Interfaces:**
- Consumes: `rag.chat(messages) -> str`, `extract_pages`, Task 1 `create_type/new_version/update_draft/approve`.
- Produces:
  - `draft_steps(pages: list[str], llm=chat) -> list[Step]`; sends `"[page N]\n..."` blocks; expects a JSON array of `{title, documents, page, unsure}`; raises `ValueError("bad draft")` on non-JSON, non-list, empty list, or an item without a string `title`. Tolerates a ```json fence. Missing `documents` becomes `[]`, `unsure` defaults `False`, `page` defaults `None`.
  - Endpoints (staff): `POST /api/track/types` multipart `name`, `file` (pdf/docx, size rules from Global Constraints) runs `draft_steps`, saves draft, returns `{version_id, steps}`; 422 `{"error": "..."}` and nothing saved on `ValueError`. `POST /api/track/types/{type_id}/versions` same with a new file. `PUT /api/track/versions/{vid}` body `{steps}` edits a draft. `POST /api/track/versions/{vid}/redraft` re-runs AI on the stored file. `POST /api/track/versions/{vid}/approve`. `GET /api/track/types` lists approved types plus drafts for staff.
  - Source files are saved under `UPLOAD_DIR/types/` with a sanitized name.

- [ ] **Step 1: Write failing tests** (a `FakeLLM` returning a canned string, like `tests/test_rag.py`):
  - `test_draft_parses_steps_with_pages_and_unsure`.
  - `test_draft_accepts_json_fence`.
  - `test_draft_rejects_garbage_empty_and_wrong_shape`: three inputs, each `pytest.raises(ValueError)`.
  - `test_draft_prompt_contains_page_markers`: the user message sent to the LLM contains `[page 2]`.
  - API: `test_bad_draft_saves_nothing_422`, `test_upload_type_creates_draft_not_live`, `test_researcher_cannot_draft_403`, `test_hostile_filename_stays_inside_upload_dir`, `test_oversize_and_wrong_ext_rejected`.
  - `test_extract_pages_one_entry_per_pdf_page` using `mock_content` fixture PDF.
- [ ] **Step 2: Run** `pytest tests/test_steps_ai.py tests/test_tracker_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Prompt asks the model to answer with JSON only, in the document's language, and to set `unsure: true` when a step or its documents are not stated. API injects the LLM through a module-level `llm = chat` that tests monkeypatch.
- [ ] **Step 4: Run** `pytest tests -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: AI-drafted step lists with staff approval"`

### Task 5: Document upload and AI screening

**Files:** Modify `tracker.py`, `steps_ai.py`, `tracker_api.py`, tests in all three test files

**Interfaces:**
- Consumes: `extract_text`, `rag.chat`, Task 2 submissions.
- Produces:
  - `find_template(doc_name: str, content_dir: Path = CONTENT_DIR) -> Path | None`: first file under a folder named `Form template` whose stem contains `doc_name` case-insensitively. `# ponytail: substring match, use an explicit template link on the step if names stop matching`.
  - `screen_document(text: str, step: Step, doc_name: str, template_text: str | None, llm=chat) -> list[dict]` each finding `{"kind": "missing"|"incorrect"|"unclear", "text": str}`; `ValueError` on bad model output.
  - `Tracker.add_upload(sid: int, step_index: int, doc_name: str, filename: str, path: str, findings: list[dict] | None, status: str) -> int` where status is one of `screened | cannot_check`.
  - `Tracker.set_upload_status(upload_id: int, status: str) -> None`; statuses `screened | cannot_check | sent | approved | returned`.
  - `Tracker.latest_uploads(sid: int, step_index: int) -> dict[str, dict]` keyed by `doc_name`, newest upload wins.
  - Endpoints: `POST /api/track/submissions/{sid}/uploads` (researcher of that submission, multipart `doc_name`, `file`) uploads to the submission's current step; `doc_name` must be in the step's `documents` (400 otherwise); returns `{upload_id, status, findings}`. `POST /api/track/uploads/{uid}/send` (researcher of that submission) sets `sent`, allowed from `screened` or `cannot_check` regardless of findings.
  - Extraction returning an empty string gives `cannot_check` with no LLM call.

- [ ] **Step 1: Write failing tests:**
  - `test_screen_parses_findings_and_rejects_bad_kind`.
  - `test_screen_prompt_includes_step_documents_and_template_when_given`.
  - `test_find_template_matches_stem_and_returns_none`.
  - API: `test_upload_returns_findings_and_screened`; `test_scanned_pdf_is_cannot_check_without_llm_call` (FakeLLM asserts zero calls); `test_llm_failure_is_cannot_check_still_sendable`; `test_send_with_findings_allowed`; `test_upload_to_foreign_submission_404`; `test_unknown_doc_name_400`; `test_reupload_replaces_latest_not_history` (`latest_uploads` returns the newer one).
- [ ] **Step 2: Run** `pytest tests -q`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** Reuse the Task 4 upload-saving and size/extension guard as one shared helper `_save_upload(file, subdir) -> Path` in `tracker_api.py`.
- [ ] **Step 4: Run** `pytest tests -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: document upload with AI screening"`

### Task 6: Staff final check and auto-advance

**Files:** Modify `tracker.py`, `tracker_api.py`, `tests/test_tracker.py`, `tests/test_tracker_api.py`

**Interfaces:**
- Consumes: Task 5 uploads, Task 2 `move_step`.
- Produces:
  - `Tracker.review_upload(upload_id: int, staff_id: str, decision: str, dismissed: list[int], note: str) -> bool`; `decision` is `approve | return`. `PermissionError` if `staff_id` is not in charge of that upload's submission; `ValueError` if upload status is not `sent` or decision is invalid. Stores dismissed finding indexes and note. Returns `True` when this approval advanced the submission (every document of the current step now has an approved latest upload, so `move_step(sid, staff_id, current_step + 1, "auto: all documents approved")` ran).
  - Endpoints: `GET /api/track/review-queue` (staff) lists `sent` uploads with findings and submission info; `POST /api/track/uploads/{uid}/review` body `{decision, dismissed, note}` returns `{advanced: bool}`. Researcher sees `returned` uploads with the note in `GET /submissions/{sid}`.

- [ ] **Step 1: Write failing tests:**
  - `test_approve_one_of_two_documents_does_not_advance`; `test_approve_last_document_advances_exactly_one_step_and_logs_event`.
  - `test_return_keeps_step_and_researcher_sees_note`.
  - `test_reupload_after_return_then_approve_advances` (old returned upload ignored).
  - `test_review_by_other_staff_403`; `test_review_unsent_upload_400`.
  - `test_dismissed_findings_stored`.
  - `test_step_with_no_documents_never_auto_advances` (staff moves it by hand).
- [ ] **Step 2: Run** `pytest tests -q`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** Advance check runs inside `review_upload` in one transaction.
- [ ] **Step 4: Run** `pytest tests -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: staff review with auto-advance"`

### Task 7: Front end, researcher side

**Files:** Create `web/track.html`, `web/track.js`, `web/track.css`; Modify `server.py` (`@app.get("/track")` returns `web/track.html`, mirror the `/admin` route), `tests/test_tracker_api.py`

**Interfaces:**
- Consumes: Tasks 3, 5 endpoints.
- Produces: page `/track` with mock login (dropdown of `MOCK_USERS` via `GET /api/track/mock-users`, public, returns `[{id, name, role}]`), and for researchers: submission list and the stepper from mockup A (done / current / upcoming, step dates from `events`, staff in charge, documents needed for the current step, upload button per document, findings list, "send to staff" button always enabled, returned-note display). Thai text. Reuse `admin.css` variables for look and feel where they exist.

- [ ] **Step 1: Write failing tests:** `test_track_page_served_200` and `test_mock_users_endpoint_lists_roles`.
- [ ] **Step 2: Run** `pytest tests/test_tracker_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the page and endpoint. Vanilla JS, `fetch`, no build step, like `web/admin.js`.
- [ ] **Step 4: Run** `pytest tests -q` (PASS), then `./run.sh`, open `http://localhost:8000/track`, log in as a researcher seeded via Task 8's staff screen or a temporary `curl`; confirm the stepper matches mockup A. Expected: current step highlighted, upload shows findings, send works.
- [ ] **Step 5: Commit** `git commit -am "feat: researcher tracking page"`

### Task 8: Front end, staff side

**Files:** Modify `web/track.html`, `web/track.js`, `web/track.css`

**Interfaces:** Consumes Tasks 3, 4, 6 endpoints. Produces staff screens: all-submissions list, create-submission form (type picker from approved types, researcher multi-select, staff in charge), move-step control on a submission, type-draft screen from mockup `staff-steps-review.html` (upload type document, steps with source page, `unsure` highlighted, edit titles and documents, add step, Re-draft, Approve and publish), review queue from mockup `document-check.html` right side (findings with agree/dismiss, note, Approve / Return).

- [ ] **Step 1:** Add the staff views; role from `GET /api/track/me` decides which view shows.
- [ ] **Step 2: Run** `pytest tests -q`. Expected: PASS (no back-end change).
- [ ] **Step 3: Verify end to end by hand** with `./run.sh` and a real LLM key or local model: as staff upload `content/CMU Presidential Scholarship/shareable/*.pdf`, review the draft, approve; create a submission for r1; as r1 upload a DOCX for step 1's document, send; as staff approve; confirm r1's stepper moves. Expected: each hop works with no console errors.
- [ ] **Step 4: Commit** `git commit -am "feat: staff tracking screens"`

### Task 9: Housekeeping

**Files:** Modify `.gitignore` (`tracker.db`, `uploads/`), `FRAMEWORK.md`

- [ ] **Step 1:** Add the ignore lines; confirm `git status` shows neither after a test run.
- [ ] **Step 2:** Document the new modules and behaviours in `FRAMEWORK.md` (versions pinning, who may move steps, Approve auto-advance, `cannot_check`, mock login ceiling).
- [ ] **Step 3: Run** `pytest tests -q` then `graphify update .`. Expected: all PASS.
- [ ] **Step 4: Commit** `git commit -am "docs: framework notes for tracking, ignore tracker data"`

---

## Self-Review

- Spec coverage: researcher stepper (T7), staff updates (T2/T3/T8), AI step draft + approval (T4/T8), per-type steps and version pinning (T1/T2), two-stage check with send-anyway (T5/T6), mock login (T3), staff create submissions and shared researchers (T2/T3), history log and back/forward moves (T2), upload limits and `cannot_check` (T4/T5), no notifications and no reassign (omitted on purpose).
- Types: `Step`, `Tracker` method names, and status strings (`screened | cannot_check | sent | approved | returned`) are the same in every task.
- Proportion: plan stays signatures, test names and assertions; bodies are left to the implementer.
