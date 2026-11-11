# Office RAG Chatbot

Local Thai chatbot (FastAPI backend + plain HTML/CSS/JS page in `web/`) over office documents. Answers in Thai from the indexed documents only, says "not found" plus the HR contact otherwise, and hands over a file only when asked and only if it is marked downloadable.


## Setup
1. Install [Ollama](https://ollama.com), then:
   ```
   ollama pull bge-m3
   ```
   Chat uses the OpenAI API (`gpt-5.4-nano`): put `OPENAI_API_KEY=sk-...` in a gitignored `.env` file. To try a local model instead, `ollama pull qwen3:8b` and start with `RISA_CHAT_BASE_URL=http://localhost:11434/v1 RISA_CHAT_MODEL=qwen3:8b` (any OpenAI-compatible server works); compare with `python -m evals.run_eval`.
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (add `-r requirements-dev.txt` instead to run the tests)

## Content folder
Put **only documents every staff member may see** in `content/` (path set by `CONTENT_DIR` in `app/core/config.py`). Never put salary, management, or other restricted files there: the bot trusts this folder completely.

- Category = first-level subfolder name (`policy/`, `forms/`, `projects/`). Top-level files are `general`.
- A file is downloadable on request only if a folder in its path is named `shareable` (for example `forms/shareable/expense-claim.pdf`). Everything else is answer-only.
- Supported: PDF, DOCX, XLSX, PPTX, TXT, Markdown. Others (including old .xls and .ppt) are skipped with a warning. Scanned (image-only) PDFs are skipped: there is no OCR.
- `python scripts/make_mock_content.py` regenerates the mock documents.
- `python scripts/seed_demo_data.py` fills `tracker.db` with demo work (6 request types, 13 requests in every state, 40 documents with AI findings and return notes, notifications, profiles) so the staff and researcher screens are not empty. Safe to run again. Log in as `somchai` or `nida` (researcher view) and `malee`, `anan` or the `RISA_DEV_LOGIN` staff (staff view); the demo accounts need `RISA_PASSWORD_R1/_R2/_S1/_S2` while `RISA_PUBLIC_URL` is set. Delete `tracker.db` and `uploads/demo/` to start clean.

## Run
Easiest: `./run.sh`. It starts Ollama if it is off, pulls `bge-m3` if missing, refreshes the index, then starts the server (app http://localhost:8000, chat http://localhost:8000/chat). Or by hand:
```
.venv/bin/python -m app.rag.ingest          # build or refresh the index (re-run after files change)
.venv/bin/uvicorn app.api.server:app --port 8000   # chat page at http://localhost:8000
```
Server later: same code, add `--host 0.0.0.0` to expose on the office LAN. Restart the server after changing `app/core/config.py`. Change models in `app/core/config.py` (`CHAT_MODEL`, `EMBED_MODEL`) and the HR contact in `HR_CONTACT` (placeholder now).

People and roles live in the `users` table in `tracker.db` (no passwords there). Demo logins (`MOCK_USERS` in `app/core/config.py`, copied into `users` at start): researchers `somchai` / `somchai123`, `nida` / `nida123`; staff `malee` / `malee123`, `anan` / `anan123`. Set `RISA_SESSION_SECRET` in `.env` to keep logins across restarts. Demo only: when `RISA_PUBLIC_URL` or `RISA_COOKIE_SECURE` is set, a demo account that still has its demo password is switched off (the server log says which); to use one, set `RISA_PASSWORD_R1`, `_R2`, `_S1`, `_S2` in `.env` (they replace the demo passwords) and, behind HTTPS, `RISA_COOKIE_SECURE=1`. Access is closed: only people staff add in the ผู้ใช้ tab can log in (paste emails, pick a role; ปิดใช้งาน removes access and keeps history). Until CMU login exists, `RISA_DEV_LOGIN=you@cmu.ac.th:password` in `.env` lets that one listed email log in with that password (dev only, never on a shared server). Put the first staff's email in `RISA_STAFF_EMAILS` (comma separated) in `.env` so someone can log in and add the rest. A login ends after 30 minutes without use (`RISA_IDLE_MINUTES` changes it) and never lasts more than 8 hours; 5 wrong tries per IP and username lock that login for 5 minutes.

## Project layout
```
app/core/      config, auth, state (settings, login, shared singletons)
app/api/       server, admin (FastAPI app and the file-manager API)
app/rag/       extract, chunk, ingest, store, rag, docmeta (documents -> index -> answers)
app/features/  tracker, tracker_api, my_requests, downloads, forms_ai, steps_ai
web/           frontend (html, css, js)      tests/ evals/ scripts/ docs/
content/       documents; only the `shareable/` folders are tracked by git
```
Run modules from the repo root: `python -m app.rag.ingest`, `uvicorn app.api.server:app`.

## Manage files (files tab in the staff workspace)
Log in as staff at http://localhost:8000 and open the คลังเอกสาร tab. It works like a drive: folders (= categories, one level) with a breadcrumb; drag files onto the list or a folder to upload; tick rows to move (drag onto a folder, or "ย้ายไป…") or bulk-delete; double-click a name to rename; the per-row switch makes a file downloadable through chat (it moves the file into `shareable/`). Every change saves at once and the server re-builds the index by itself 2.5 s after the last change, even if the admin tab is closed (chat keeps answering while it runs). Emptied folders disappear. Same-name uploads replace the old file. Without `ADMIN_PASSWORD` the page works only from the server machine itself (loopback). To expose it, start the server with `ADMIN_PASSWORD=<long random string>`; the browser then asks for a login (user `admin`). Set it on any deployed server: behind a reverse proxy on the same machine every visitor looks like loopback, and a set password is the only thing that stops them. Serve over HTTPS, since Basic auth sends the password in every request. Admin writes with a foreign `Origin` header are rejected (CSRF), and without a password the `Host` header must also be loopback (DNS rebinding); a proxy that rewrites `Host` must keep the browser's `Origin` host the same.

## Check correctness
```
.venv/bin/pytest                          # unit tests, no Ollama needed
.venv/bin/python -m evals.run_eval        # live question set, needs Ollama + ingest
.venv/bin/python -m evals.load_test --users 5
```
Tuning knobs in `app/core/config.py`: `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MAX_DISTANCE`.

## Notes
- PDF extraction uses `pymupdf` (AGPL, fine for internal use); it read Thai from the mock PDF. Re-check with the real Thai files.
- Live results (Mac M5, 16GB, `qwen3:8b` + `bge-m3`, mock content): `python -m evals.run_eval` passes 10/10; first question took ~12s including model load. Not yet measured: multi-user latency (`evals.load_test`) and quality on real Thai documents. `qwen3:8b` is the placeholder tag; settings in `app/core/config.py` are untuned beyond the mock set.

## LINE chatbot
Create a LINE Official Account, enable the Messaging API, then put `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` and `RISA_PUBLIC_URL` (the https address of this server) in `.env` and restart. In the LINE Developers Console set the Webhook URL to `<RISA_PUBLIC_URL>/api/line/webhook`, turn on Use webhook, and turn off LINE's auto-response messages. A researcher links their LINE account with the เชื่อม LINE button on their profile page. Locally, `cloudflared tunnel --url http://localhost:8000` gives a temporary https address. LINE also pushes alerts, only the ones that need action and only to the person concerned: researchers get a returned document, a step move and a finished request; staff in charge get documents waiting for review (one push per batch) and new assignments. Everything else stays in the website bell.
