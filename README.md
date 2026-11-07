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
Put **only documents every staff member may see** in `content/` (path set by `CONTENT_DIR` in `config.py`). Never put salary, management, or other restricted files there: the bot trusts this folder completely.

- Category = first-level subfolder name (`policy/`, `forms/`, `projects/`). Top-level files are `general`.
- A file is downloadable on request only if a folder in its path is named `shareable` (for example `forms/shareable/expense-claim.pdf`). Everything else is answer-only.
- Supported: PDF, DOCX, XLSX, PPTX, TXT, Markdown. Others (including old .xls and .ppt) are skipped with a warning. Scanned (image-only) PDFs are skipped: there is no OCR.
- `python scripts/make_mock_content.py` regenerates the mock documents.

## Run
Easiest: `./run.sh`. It starts Ollama if it is off, pulls `bge-m3` if missing, refreshes the index, then starts the server (app http://localhost:8000, chat http://localhost:8000/chat). Or by hand:
```
.venv/bin/python ingest.py          # build or refresh the index (re-run after files change)
.venv/bin/uvicorn server:app --port 8000   # chat page at http://localhost:8000
```
Server later: same code, add `--host 0.0.0.0` to expose on the office LAN. Restart the server after changing `config.py`. Change models in `config.py` (`CHAT_MODEL`, `EMBED_MODEL`) and the HR contact in `HR_CONTACT` (placeholder now).

Demo logins (`MOCK_USERS` in `config.py`): researchers `somchai` / `somchai123`, `nida` / `nida123`; staff `malee` / `malee123`, `anan` / `anan123`. Set `RISA_SESSION_SECRET` in `.env` to keep logins across restarts. Demo only: change before anyone else can reach the app.

## Manage files (📁 tab in the staff workspace)
Log in as staff at http://localhost:8000 and open the 📁 ไฟล์ความรู้ tab. It works like a drive: folders (= categories, one level) with a breadcrumb; drag files onto the list or a folder to upload; tick rows to move (drag onto a folder, or "ย้ายไป…") or bulk-delete; double-click a name to rename; the per-row switch makes a file downloadable through chat (it moves the file into `shareable/`). Every change saves at once and the server re-builds the index by itself 2.5 s after the last change, even if the admin tab is closed (chat keeps answering while it runs). Emptied folders disappear. Same-name uploads replace the old file. Without `ADMIN_PASSWORD` the page works only from the server machine itself (loopback). To expose it, start the server with `ADMIN_PASSWORD=<long random string>`; the browser then asks for a login (user `admin`). Set it on any deployed server: behind a reverse proxy on the same machine every visitor looks like loopback, and a set password is the only thing that stops them. Serve over HTTPS, since Basic auth sends the password in every request. Admin writes with a foreign `Origin` header are rejected (CSRF), and without a password the `Host` header must also be loopback (DNS rebinding); a proxy that rewrites `Host` must keep the browser's `Origin` host the same.

## Check correctness
```
.venv/bin/pytest                          # unit tests, no Ollama needed
.venv/bin/python -m evals.run_eval        # live question set, needs Ollama + ingest
.venv/bin/python -m evals.load_test --users 5
```
Tuning knobs in `config.py`: `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MAX_DISTANCE`.

## Notes
- PDF extraction uses `pymupdf` (AGPL, fine for internal use); it read Thai from the mock PDF. Re-check with the real Thai files.
- Live results (Mac M5, 16GB, `qwen3:8b` + `bge-m3`, mock content): `python -m evals.run_eval` passes 10/10; first question took ~12s including model load. Not yet measured: multi-user latency (`evals.load_test`) and quality on real Thai documents. `qwen3:8b` is the placeholder tag; settings in `config.py` are untuned beyond the mock set.
