# RiSA Dashboard: Workflow & Status Tracking and Document Check

Status: DRAFT for approval. Mockups: `.superpowers/brainstorm/45921-1793946993/content/` (`tracking-layout.html`, `staff-steps-review.html`, `document-check.html`).

## Intent and why

The meeting named three functions for the RiSA AI chatbot. Function 1 (Automated Q&A) is built: FastAPI `server.py`, RAG in `rag.py`, OpenAI-compatible chat via `config.py`, admin in `admin.py` and `web/admin.*`.

This design covers functions 2 and 3:

2. **Workflow & Status Tracking.** Show the steps of a submission (scholarship, funding), the documents to prepare, and which step the submission is at.
3. **Document Check.** Analyse an uploaded document for missing, incorrect, or unclear information and warn the user at once.

Why: today researchers and professors ask staff in person to learn where a submission stands. The current step lives only in staff members' memory. Nothing records it.

## Goals

- A researcher sees, without asking anyone, the step list and current step of each of their submissions.
- Staff in charge of a submission record its progress in the dashboard. Staff are the source of truth for the current step.
- A new scholarship or funding type needs no code change. Staff upload its document, AI drafts the step list, staff approve it.
- A researcher uploads a document and gets one AI screening result immediately. Staff then make the final check.

## Non-goals

- Real CMU email login. Only a mock login page with mock IDs now. Real login comes later.
- LINE integration. Not discussed. Out of scope here.
- AI deciding a step is complete. Only staff move a submission forward.
- Automatic status updates from outside systems.

## Anti-goals (failure even if it technically works)

- AI-drafted steps going live without staff approval.
- AI findings blocking a researcher. Researcher can always send anyway.
- A researcher seeing another researcher's submissions.
- Staff finding the dashboard slower than telling people by chat. Updating a step must be one click.

## Decided by the user

- **Researcher view = stepper** (mockup A): one submission, vertical list of steps, done / current / upcoming, dates, staff in charge, documents needed for the current step. A table of all submissions was rejected.
- **Staff update status.** The staff member in charge of a submission moves it forward.
- **Steps differ per submission type** and new types will keep arriving.
- **AI drafts steps from an uploaded type document; staff must approve before it is live.** Each drafted step shows its source page. Low-confidence steps are highlighted. Staff can edit, add, re-draft.
- **Document check = two stages.** AI screens once on upload (findings: Missing / Incorrect / Unclear). Researcher can fix and re-upload, or send anyway. Staff then do the last check: agree or dismiss each AI finding, add a note, then Approve (advances the stepper) or Return for fixes.
- **Mock login now:** a login page with mock IDs for researcher and staff roles. Real CMU email accounts later.
- Existing code is reused: same chat endpoint config, same document extraction (`extract.py`), same FastAPI app.

## Constraints

- Python/FastAPI app with static front end in `web/`. Match existing style, no new framework unless unavoidable.
- Chat model is `gpt-5.4-nano` via `RISA_CHAT_BASE_URL`, or a local Ollama model. Prompts must work with a small model and return structured output.
- Documents are mostly Thai (PDF, DOCX). Extraction must handle Thai. Steps and findings display in the document's language.
- The repo is private on GitHub, but real researcher documents must not be committed.

## Left to the builder (flagged as my calls where marked)

- Data storage. My call: a local SQLite file, git-ignored like `index/`, since the app has no database for tracked data today.
- Mock login mechanism. My call: a session cookie set from a fixed list of mock users (a few researchers, a few staff). Designed so real CMU login replaces only that list.
- Whether uploaded researcher documents live on disk next to `content/` or elsewhere. My call: separate git-ignored folder.
- What AI checks a document against. My call: the documents-needed list and source text of the approved step, plus the matching form template in `content/Form template/` when one exists. Open question below.
- Staff-in-charge assignment: my call, set per submission when it is created, one staff member.

## Calls made after builder review

Decided by the user:
- **Staff create submissions** for researchers (staff pick type, researchers, staff in charge). Researchers cannot create.
- **Several researchers can share one submission.** All of them see it. Researchers see only submissions they belong to.

My calls (change if wrong):
- Staff see all submissions. Only the staff in charge can update a submission (step moves, Approve, Return).
- AI draft also lists documents needed per step. Staff edit them.
- Each step change is logged with date and staff. Staff can move forward or backward. Approve in document check also advances.
- Editing a type's steps never changes in-flight submissions. They keep the version they started with.
- Uploads belong to the current step. A step may need several documents, each checked separately. Approve advances only when all documents of the step are approved.
- No notifications for now. No staff reassign for now.
- Uploads: PDF and DOCX only, max 10 MB. Scanned PDF with no text: show "cannot check", researcher can still send anyway.

## Next

After approval: implementation plan via `superpowers:writing-plans`.
