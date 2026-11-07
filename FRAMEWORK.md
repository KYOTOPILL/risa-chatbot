# RiSA: how the framework works

RiSA is a Thai-language chatbot that answers staff questions from company documents and sends the files they ask for.
Stack: FastAPI + plain HTML/JS, Chroma vector store, local `bge-m3` embeddings (Ollama), chat model `gpt-5.4-nano` via OpenAI by default; `RISA_CHAT_BASE_URL` + `RISA_CHAT_MODEL` point it at any OpenAI-compatible server (e.g. local Ollama `qwen3:8b`).

## 1. The big picture

```
 content/<topic>/...            (admin uploads, edits, deletes files)
        |
        v
  ingest.build_index  --->  Store (Chroma)
   - extract text (+docx tables,xlsx,pptx) - "docs"  collection: text chunks     (for answering questions)
   - chunk 800/100            - "names" collection: one entry per   (for finding files)
   - embed (bge-m3)             downloadable file = name + Thai summary
   - LLM summary (new files)
        |
        v
  rag.answer(history, message, store)
   LLM + 4 tools  ->  Reply(text, file_doc_ids, sources)
        |
        v
  server.py  /api/chat/stream  ->  web/app.js shows text as it is written + file names as download links
```

Two ideas carry the whole design:

1. **Two indexes.** Question answering searches the document text. File requests search a separate index of file names plus short Thai summaries, because file names are English and staff ask in Thai.
2. **The LLM routes, code only guards.** The model decides which tool to call. Code validates the result. There are no keyword lists or regex rules for intent.

## 2. What was built, in order

| Step | What changed |
|---|---|
| Model | Local LLM replaced by the OpenAI API, cheapest working model (`gpt-5.4-nano`, `reasoning_effort: "none"`). Key lives in `.env`. |
| UI | 20 polish items in `web/` (shortcut hint, skeleton rows, undo toast, view transitions, safe-area, and more). Welcome chips are general questions. |
| Cleanup | Unused Ollama models and RAGAS lines removed. `.env` loader added to `config.py`. |
| File requests | Files shown as named links, not a button. No asking "which file". List requests send all matches. |
| Name index | Each file gets an LLM-written Thai summary (kept even when downloadable is off); downloadable ones are searchable by it. File search matches name plus summary. |
| Incremental indexing | Only new or changed files are re-embedded and re-summarised. Built for about 500 documents. |
| Topic folders | The first non-`shareable` folder is the file's topic and acts as a soft filter. |
| Tool-based routing | Rules and regexes deleted. The model calls tools. Eval score went from 17/24 to 22/24. |
| Cost cuts | Token usage logging, answer cache for repeated questions, output cap. See section 5. |

## 3. The functions that were added

### `rag.py` (the brain)

| Function / constant | Job |
|---|---|
| `answer(history, message, store, llm)` | Runs the tool loop and returns a `Reply`. Everything else supports this. |
| inner `run(name, args)` | Executes one tool call against the store and returns text for the model. |
| `chat_tools(messages, tools, tool_choice)` | One OpenAI call with tool support. `chat()` is the plain version, still used for summaries. |
| `chat_tools_stream(..., on_delta)` | Same call with `stream: true`; answer text goes to `on_delta` as it arrives, tool-call fragments are joined, token usage is still counted. `on_delta(None)` means the text so far was not the answer (a tool call followed). `answer(..., llm=chat_tools_stream, on_delta=...)` streams only the final round, and `_hold_markers` keeps `NOT_FOUND` / `OUT_OF_SCOPE` from showing before they are swapped for the Thai message. |
| `AGENT_SYSTEM` | System prompt in four labeled sections: ROLE, TOOLS, RESPONSE GUIDELINES, FORMAT. The guidelines are the lessons from fixing real answers: answer only the exact thing asked (related is not the same); if documents only cover a related subject, say so and name what does exist; overview questions get one sentence per topic and no file list; direct answer first, lists only for 3+ items, about 8 lines at most; exact numbers; dates only for status questions; `NOT_FOUND` only when nothing relevant exists, `OUT_OF_SCOPE` for off-topic; Thai only, no markdown, polite `ค่ะ`. When a new lesson comes up, add it to the guidelines (and a case to `evals/questions.json`), not a one-off patch. |
| `TOOLS` | The four tool definitions below. |
| `_dedupe`, `_context` | Drop overlapping chunks and format search results with their modified date. |
| `is_mostly_thai` | Detects an English reply so it can be retried once in Thai. |
| `Reply`, `Turn` | Result and history dataclasses. |
| `usage` | Running totals of calls, prompt tokens and completion tokens, filled by `_post` from OpenAI's `usage` field. `evals/run_eval.py` prints it. |
| `_glossary()` | Reads `glossary.txt` (project root, one `term = meaning` per line, `#` lines skipped) and appends it to the system prompt on every answer, so a term the model would translate wrongly (for example `settlement` = first-arrival allowance, not repayment) has a fixed meaning. Edit the file, no restart needed. |
| `MAX_ANSWER_TOKENS` | Output cap (600) sent as `max_completion_tokens` by `chat_tools`. Summaries use `chat()` and are not capped. |

The four tools:

| Tool | When the model uses it | What it returns |
|---|---|---|
| `search_documents(query, topic?)` | Questions about what documents say | Up to `TOP_K=4` chunks, fenced in `<context>`, hits over `MAX_DISTANCE=0.6` dropped |
| `find_files(query, topic?)` | User asks for or asks about a file | Up to `FIND_K=8` candidates as `f1 \| name \| topic \| summary` |
| `send_files(file_ids)` | After `find_files`, to attach files | Confirmation. Only ids from this turn's `find_files` are accepted |
| `list_topics()` | Vague "what documents do you have" | Each topic folder with its file count, file names and short Thai summaries (`Store.topic_files()`), so the bot can summarize what each topic holds and then ask which one |

Guards in code (the model cannot bypass them):
- Round 0 forces a tool call (`tool_choice="required"`). Loop is capped at `MAX_ROUNDS=4`.
- Invented file ids are ignored. At most `MAX_FILES=8` files are sent.
- Thai-only check with one retry, then fall back to the HR contact message.
- Files sent but empty text gives `FILE_READY`. Nothing found gives `NOT_FOUND` (HR contact message). An off-topic question gives `OUT_OF_SCOPE`: "คำถามนี้ไม่เกี่ยวข้องกับเอกสารที่มีอยู่" plus the HR contact. The model decides which, so an office question the documents do not cover can occasionally come back in the model's own words instead of the HR message.
- Search results are wrapped as data, so instructions inside documents are ignored.
- If the model picks the wrong topic, the search also runs across all topics.

### `store.py` (the memory)

| Function | Job |
|---|---|
| `Store.update(items, keep)` | Embed only changed docs, delete removed ones. |
| `Store.signatures()` | Returns `size:mtime_ns` per file so unchanged files are skipped. |
| `Store.find_files(question, k, category)` | Searches the `names` collection (name plus summary). |
| `Store.topic_files()`, `categories()` | Topic folders and how many downloadable files each has. |
| `Store.doc_path()` | Maps an id to a path. The server uses it to show file names. |
| `Store.cached_summary(sig)`, `remember_summary(sig, text)` | Summaries remembered by file signature (size + mtime) in `index/summaries.json`. Moving or renaming a file, or switching downloadable off and on, keeps the same content, so it keeps its summary and costs no new API call. `ingest.build_index` reads this before calling the LLM, and `/api/admin/files` falls back to it so a non-downloadable file still shows its description. |
| `Store.summaries(ids=None)` | doc_id to Thai summary for downloadable files. Used by `/api/chat` (file cards) and `/api/admin/files`. |
| `NameHit` | Result row for file search. |

### `ingest.py` and `docmeta.py` (the intake)

- `build_index(content_dir, store, summarize)` walks `content/`, skips files whose signature is unchanged, and returns `{"indexed","changed","skipped"}`.
- `summarize(text)` asks the model for a Thai summary once for every new or changed file, downloadable or not, and remembers it by file signature, so a description never depends on the downloadable switch. A file whose summary is missing (for example indexed before this rule, or a failed call) is indexed again on the next reindex. Only downloadable files' summaries go into the name index used by file requests. A failure is logged and the file is still indexed.
- `DocMeta` gained `summary` and `sig`.
- `extract.py`: `extract_text` reads PDF (pymupdf), DOCX (`_docx`: paragraphs and tables in document order, a table row is one line of cells joined by ` | `, merged cells counted once, nested tables not read), XLSX (`_xlsx`), PPTX (`_pptx`), TXT and MD. `_xlsx` writes one paragraph per row as `[Sheet] Header: value | Header: value` (first non-empty row is the header, empty rows and cells are skipped, at most `MAX_SHEET_ROWS=3000` rows per sheet, cached formula values), so chunking never cuts a row and each value keeps its column name. `_pptx` writes one paragraph per slide: text boxes, tables (cells joined by ` | `), grouped shapes and speaker notes; slides with no text are skipped. Old `.xls` and `.ppt` are not supported (`SUPPORTED_EXTS` in `config.py`, also the upload picker in `admin.html`). New dependencies: `openpyxl`, `python-pptx`.

### Tracking dashboard (`tracker.py`, `steps_ai.py`, `tracker_api.py`, `web/home.*`)

Goals 2 and 3 of the meeting: step tracking and document check. Open `/`. Spec: `docs/superpowers/specs/2026-11-06-tracking-and-document-check-design.md`.

- `tracker.py` (`Tracker`, SQLite file `tracker.db`, git-ignored): all rules, no web or LLM code. A type has numbered versions, `draft` or `approved`. `create_submission` needs an approved version and at least one researcher; the submission keeps that version, so editing a type later never changes it. `list_submissions` and `get_submission` return only the researcher's own submissions (staff see all); a foreign id gives `None`. `move_step` is only for the staff in charge, goes forward or back, `to_step == step_count` means done, and every move is logged in `step_events`. `add_upload` / `latest_uploads` keep every upload and treat the newest per document as current. `review_upload(approve|return)` returns `True` when the approved document was the last one of the current step: then it moves the submission one step on by itself. A step with no documents never advances by itself. Step lists are validated (`validate_steps`: non-empty, each step has a title and a documents list). A document that is `sent` or `approved` cannot be uploaded again. `send_upload` and `review_upload` change status only from the expected state, and the auto-advance fires only for the request that still sees the old step.
- `steps_ai.py`: `draft_steps(pages)` asks the model for a JSON list of steps (`title`, `documents`, `page`, `unsure`) from a scholarship document and raises `ValueError` on anything that is not that shape. `screen_document(...)` returns findings of kind `missing`, `incorrect` or `unclear`. `find_template(doc_name)` finds a blank form under `Form template/` by file-name substring. The model is a parameter (default `rag.chat`).
- `tracker_api.py` (`/api/track/...`): username and password login against `MOCK_USERS` in `config.py` (demo passwords in plain text); the `uid` cookie is `id.HMAC` signed with `RISA_SESSION_SECRET` (random at start if unset, so logins end on restart). `GET /mock-users` needs a login and never returns passwords. `auth.py` holds `User`, `authenticate`, `session_value`, `current_user` and `require_staff`, the one place to swap for CMU login; both `tracker_api.py` and `admin.py` use it). Staff create types, drafts and submissions; AI step drafts stay `draft` until staff press approve. Posts: staff turn on เปิดรับ for an approved type (`POST /types/{id}/publish`, owner = whoever publishes unless `owner_id` names another staff member; `POST /types/{id}/close`; columns `open` and `owner_id` on `types`, added to old databases at start). Every logged-in user can read `GET /open-types`; a researcher starts their own request with `POST /open-types/{id}/start` (their own submission from the newest approved version, titled "Type - Name", staff in charge = the owner; one request per researcher per post: starting again returns the existing request, which the researcher keeps editing by re-uploading until the document is sent). Closing hides the post and keeps existing requests. Staff delete a draft (`DELETE /versions/{id}`; the type goes too when it was its last version) or a whole type with its forms (`DELETE /types/{id}`); both give 409 while any request uses it, and remove the source files. Staff can still create a request for a named person in งานทั้งหมด. Slow AI steps show progress: the endpoints that call the model (`POST /types`, `/types/{id}/versions`, `/versions/{id}/redraft`, `/types/{id}/forms/draft`, `/submissions/{id}/uploads`, `/submissions/{id}/forms`) run through `tracker_api._progress`. A client that sends `Accept: application/x-ndjson` gets JSON lines `{"status": text}` for each real step (pages read, characters, AI working, fields or findings found), then `{"done": result}` or `{"error": text}`; any other client gets the plain JSON as before. Uploaded files are saved and form answers validated before the stream starts, so those errors stay plain 4xx. In the page, `apiStream` reads the lines and `runProgress` (home.js) replaces the clicked card with a checklist of finished steps and the seconds the current one has taken, with a back button on error. Online forms (table `forms`, one row per type and document: title, `fields`, status `draft` or `approved`). A field is `{key, label, hint, type, required, options}` with type text, longtext, number, date, choice or file; `validate_form` in `tracker.py` fills defaults and keeps keys stable when staff relabel. In the staff tab ประเภทงาน, each type has one page (list row, then จัดการ) with its steps and documents, its forms and its เปิดรับ controls; there staff press AI สร้างฟอร์ม (`POST /types/{id}/forms/draft`; `forms_ai.draft_form` reads the type's guide file plus the document name; 502 and nothing saved if the model gives nothing usable), edit in the editor with a live preview (`PUT /types/{id}/forms`; an approved form stays approved) and approve (`POST .../forms/approve`). No Word file is made. A document with an approved form is filled in on the website: `GET /submissions/{id}` returns `forms` as `{doc: {title, fields}}` and the researcher saves answers with `POST /submissions/{id}/forms` (multipart: `doc_name`, `answers` JSON, `file_keys` + `files` for file fields; photos .jpg/.png allowed there). The server checks required, number, date and choice, stores a snapshot of label, type and value in `uploads.answers` (so later form edits never change what staff review) and runs the AI check on the answers text. Saving again replaces the answers (earlier attachments stay unless a new one is chosen) until the document is sent. Sent forms follow the same send, review and auto-advance flow as file uploads; staff see the answers and open attachments through `GET /uploads/{id}/answer-file?key=` (same access rules as the upload). A document with no approved form keeps the plain `.pdf`/`.docx` upload; the plain upload is refused for a document that has a form. Plain uploads: researchers upload `.pdf` or `.docx` (max 10 MB, name sanitized, stored under `uploads/`, git-ignored) for the current step; AI screens once; the researcher may send even with findings. A scanned PDF or a bad model answer gives status `cannot_check`, which can still be sent. Staff see the queue, open the file, dismiss findings, then approve or return with a note.
- Pages (spec `docs/superpowers/specs/2026-11-07-two-screen-redesign-design.md`): one login at `/`, then the role decides the screen. `/chat` is the chat page (`web/index.html`, `app.js`), for logged-in researchers only: anonymous visitors and staff are redirected to `/`, and `/api/chat` and `/api/chat/stream` answer 401 (no login) or 403 (staff) via `auth.require_researcher`. The chat knows the asker: `rag.answer(..., me=...)` adds a `my_requests` tool whose result is `my_requests.describe(tracker, user_id)` (that researcher's requests: step, documents, status, AI notes, staff in charge, never anyone else's). A reply that used it is `Reply.personal` and is never put in the shared question cache. `/track` and `/admin` redirect to `/`. The file manager is no longer a page: it is the 📁 คลังเอกสาร tab of the staff workspace and its API (`/api/admin/*`) is guarded by the staff mock login, which has no password. So anyone who can reach the site can become staff and edit the knowledge files; real CMU login must come before the app is exposed. The pages link to each other: home header has `แชทกับ AI` (`/chat`, shown to researchers only), `/chat` has `หน้าหลัก` (`target="_top"` so it leaves the drawer iframe).
- Page map (2 HTML pages plus one fragment):

  | File | URL | Who | Login |
  |---|---|---|---|
  | `web/home.html` | `/` | researchers and staff | username and password |
  | `web/index.html` | `/chat` | researchers | login (others go to `/`) |
  | markup in `web/home.html` (`#files-root`, hidden) | none (the files tab of `/`) | staff | staff login |

  ```
                    ┌──────────────── / (home.html) ────────────────┐
                    │  login → researcher home  OR  staff workspace │
                    │            (staff menu: files tab)  │
                    └───────┬───────────────────────────────────────┘
          header "แชท" link │
          (all logged in)   ▼
                    /chat (index.html)
                            │ "หน้าหลัก"
                            └──────► /

     Researcher home also embeds /chat in the chat drawer (iframe);
     there "หน้าหลัก" uses target="_top" so it leaves the iframe.
  ```

  Each page calls: home `/api/track/*` and `/api/admin/*` (staff, files tab); chat `/api/chat/stream` and `/download/{doc_id}`.
- Look: the original teal palette (`--accent` #0f766e, warm off-white `--bg`) with the cleaner shapes (8-12px corners, 1px borders, soft shadows, no emoji). All colours are tokens in the `:root` block of `style.css`, with a dark set; `icons.js` has `icon(name)` for the menu and chat button (one stroke width).
- `web/home.html`, `home.js`, `home.css`, `todo.js`: Thai UI, text always set with `textContent`. Login screen: username and password form (same form for both roles; the account decides the screen), wrong login shows an inline message. Phones: both pages carry the viewport and theme-color meta; `style.css` and `home.css` end with a "phones" block (44 px tap targets on touch screens, header and rows wrap, cards wrap long text, 2x2 staff menu and a full-screen chat drawer under 480 px, the chat page hides its home link when embedded in the drawer via the `embedded` class). Not an installable app (no manifest or service worker). Researcher home: a "สิ่งที่ต้องทำ" list (`todoItems` in `todo.js`, pure and tested with node: returned documents first, then documents waiting for staff), then one stepper card per submission with upload and send inline, and a ถาม AI button (chat icon) that opens a drawer holding `/chat` in an iframe (loaded on first open; researchers only). Staff workspace: header shows an initial avatar with name and role and plain text links (แชท, ออกจากระบบ); left menu is a plain list with SVG icons and a divider: รอตรวจสอบ (count badge, opens first), งานทั้งหมด, then ประเภทงาน, คลังเอกสาร (the file manager, mounted once by `mountFiles()` from `files.js` on the `#files-root` markup that ships inside `home.html`; it stays in the page, hidden, when another tab shows). The inbox has a title, a numbers row (waiting, open submissions, documents waiting over 7 days counted from upload time; `staffStats` in `todo.js`, shown only when something waits) and a friendly empty state; `agoText` gives the Thai "sent N ago". Review rows show the AI finding count as a badge; an upload that could not be checked also shows no findings, so the label says "(หรือตรวจไม่ได้)" because status `sent` no longer records `cannot_check`.
- Known limits: the login is a demo (plain-text passwords in `config.py`, no HTTPS or Secure cookie, no rate limit, no lockout); staff cannot reassign a submission; no notifications; template match is a file-name substring; step changes by two staff at once are not locked.

### Other files

- `server.py`: `/api/chat/stream` is what the page uses: JSON lines `{"status": text}` while a tool runs, `{"delta": text}` while the answer is written (`{"delta": null}` = discard it), then `{"done": true, "text", "files"}` or `{"error": text}`. It runs `answer` in a thread and relays its deltas through a queue; cache, per-IP slot, and logging match `/api/chat`. The final `text` replaces what streamed, since marker and language fixes can change it. `/api/chat` is the same answer in one JSON response (tests, evals, load test) and returns `{"text", "files": [{"id","name"}]}`. A question with no history is looked up in `state.cache` (key: lower-cased, whitespace-normalized message) before any OpenAI call.
- `state.py`: `cache` (up to `CACHE_MAX=500` replies, no expiry) is cleared by `admin.reindex`, so a changed index never serves old answers. Questions with history are never cached, and failed answers are never cached.
- `web/icons.js`: `fileIcon(name)` returns an inline SVG icon (page with folded corner and a coloured label: PDF, DOC, XLS, PPT, TXT, or the upper-cased extension in grey) that `app.js` appends at the end of each file link. Edit `TYPES` and `COLORS` in `icons.js` to change labels or colours; size is the `.ftype svg` rule in `style.css`.
- Chat screen (`web/app.js`, `style.css`): each reply is a row with a bot avatar (RiSA), the bubble and a time stamp shown on hover (not restored after a refresh). Each file is a card (`.fcard`): type icon, name (2 lines max), Thai summary (2 lines max), `TYPE · size`, download arrow. While waiting, the bubble shows the real step from `{"status"}` lines (`rag.STATUS`: searching documents with the model's query, finding files, attaching files, then composing the answer), starting at `กำลังคิด...`, next to a spinning, pulsing four-point spark (`.spark`) with a shimmering text (`.shimmer`), both still under `prefers-reduced-motion`. The text comes from the code that runs each tool, so it costs no tokens. Old behaviour kept: renders each file as a link, and saves sent file names in history so "the other one" works.
- `admin.py`: reindex calls `build_index(..., summarize)`. Every route needs a staff login (`require_admin`: 401 not logged in, 403 not staff or cross-site POST). Debounce lives here: every successful upload, replace, delete, move, folder rename or folder delete (the `CHANGES` dependency) restarts a `REINDEX_DELAY` (2.5 s) timer that runs `reindex()`, so the index catches up even when the browser tab is closed. `GET /api/admin/index-status` returns `{state: ok|stale|busy|error, indexed, skipped, error}`; the admin page polls it every 1.5 s while stale or busy. A failed run shows `error` and the next change retries. `/api/admin/files` rows now include `summary`.
- File manager (markup in `web/home.html` under `#files-root`, script `web/files.js`; its styles live in `home.css`): breadcrumb, an index status strip (green = chat has the latest files, amber = changes waiting for the automatic reindex, spinner = updating, red = error; no button, it updates by itself; the strip shows the server's status), a selection bar that slides in only when files are ticked, folder rows (count, total size, last edit), file rows (type icon, name with a small `i` button that opens the AI-written Thai summary in a popover, and a `ดาวน์โหลดในแชท` column with an on/off switch that moves the file in or out of the `shareable` folder; the selection bar has `เปิดให้ดาวน์โหลด` / `ปิดการดาวน์โหลด` for many files at once) and a `⋯` menu per row (rename, move, replace, delete in red, with the undo toast). Uploading (button or drag and drop) first opens a dialog: `ให้ดาวน์โหลดผ่านแชทได้` is ticked by default, so new files can be found by file requests; untick it for internal-only documents. The open folder's rename and delete are in a `⋯` menu next to the breadcrumb (same menu as on the folder row). Rows are at least 52 px high. Drag and drop move, double-click rename and the automatic reindex 2.5 s after a change (now timed by the server) are unchanged.
- `config.py`: `CHAT_MODEL` (override with `RISA_CHAT_MODEL`), `SUMMARY_CHARS`.
- `evals/run_eval.py` + `evals/questions.json`: 24 real CMU-based cases. Run with `python -m evals.run_eval` (about 50 API calls).
- `tests/`: 218 tests, including `test_tracker.py`, `test_steps_ai.py`, `test_tracker_api.py` for the dashboard and `test_todo_js.py` (runs `web/todo.js` with node; skipped when node is missing). `test_rag.py` uses a scripted `FakeLLM` and `FakeStore`, so no network is needed.

## 4. One request, step by step

Staff types: "ขอใบเสร็จค่าครองชีพ" (send me the living allowance receipt).

1. `/api/chat` calls `answer(history, message, store)`.
2. The model must call a tool. It calls `find_files(query="ใบเสร็จค่าครองชีพ")`.
3. `Store.find_files` returns candidates, for example `f1 | 1 - Living Allowance - Receipt.pdf | topic: CMU Presidential Scholarship | <Thai summary>`.
4. The model reads the summaries and calls `send_files(["f1"])`.
5. Code checks `f1` is a real candidate and records the doc id.
6. The model writes one Thai sentence. Code returns `Reply(text, [doc_id])`.
7. The UI shows the sentence plus a download link named after the file.

For "ลาพักร้อนกี่วัน" the model calls `search_documents` instead and answers from the chunks. If no chunk is close enough it says `NOT_FOUND`, and the user gets the HR contact message.

## 5. Results and cost

| Setup | Score (24 cases) |
|---|---|
| Old rules + regex, nano | 17 |
| Old rules + regex, mini | 15 |
| Tools, mini | 20 |
| Tools, nano | 21 to 22 |

- Bigger model did not help, so `gpt-5.4-nano` stays. Checked again on 35 cases (with 9 hard questions: slang, typos, indirect wording): nano 29, mini 26 on the same index; `gpt-5.4-mini` answered some hard questions more carefully but lost on file requests and follow-ups. A stale index (2 files had no file-name entry) cost both models points; after re-indexing nano scores 33/35. The two open failures: `ขอใบเสร็จค่าเดินทางมา มช` also sends the hometown receipt (ambiguous), and the `settlement` conditions question still gets a made-up list instead of "not found" (`glossary.txt` fixes the meaning, not this).
- Eval noise: `gpt-5.4-nano` flips on about 3 of 35 cases between identical runs (the same question passed, then failed). Treat score differences of 3 or less as noise; repeat before judging a prompt change. Guideline rewrite scored 27, 29, 30 against 33 for the old prompt, with failures that moved between runs.
- Tool path is about 3 s per question (rules path was about 2 s).
- One summary call per new or changed file, downloadable or not. Estimated well under 1 USD for 500 files (not verified against current prices).

### Cost controls

- Embeddings are local, so they cost nothing. Summaries are one call per new or changed file.
- Chat is the recurring cost: 2 to 3 calls per question, each resending system prompt, tool schemas, history and tool results.
- Repeated first questions cost nothing (cache). Replies are capped at 600 tokens. Check real spend with the `tokens:` line printed by `python -m evals.run_eval`.
- Not done yet, see section 7: skipping the final call after `send_files`, shorter history and tool results.

## 6. Known limits

- Eval runs are noisy. One run shows plus or minus a point or two.
- Typo request "ขอดูเอหสารทุน" is ambiguous now that two topics exist.
- "All receipts" sometimes returns only some of them.
- Spam guard: one IP may have `RISA_MAX_INFLIGHT` questions being answered at once (default 2, 0 = off); more get 429 and a Thai 'still answering' message. There is no limit on how many questions it asks over time, and cached answers are free. The page sends one question at a time, so only a script flooding the API hits this, and it caps one flooder at about 2 questions per answer time (a few seconds). Behind a reverse proxy every visitor shares the proxy's IP, so run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>`, or two simultaneous users would block each other. Counts are per process.
- Chat questions run in parallel (one thread each, up to 40 in uvicorn's pool); extra ones wait in that pool. A re-index no longer blocks chat. Chat runs as one process: the answer cache is per process, so do not start several workers without moving it out.
- Image-only (scanned) PDFs are not indexed because there is no OCR.
- Spreadsheets: formulas show their last saved value (nothing if the file was never opened in Excel), charts and images are ignored, and rows past 3000 per sheet are cut. Slide images and diagrams are ignored.
- Summaries of near-identical receipt forms read alike.
- Only two topic folders exist. The topic filter is lightly tested with real data.
- No log of real staff requests exists yet. The eval set is written by hand.
- Cache has no time limit and is cleared only by reindex. Editing files in the admin without reindexing leaves old answers cached, same as the index itself.
- Cache is per process and lost on restart.
- Work is not committed yet. `content/` has uncommitted changes.

## 7. Next steps worth doing

1. Commit the tool-based migration.
2. Collect real staff requests and add them to `evals/questions.json`.
3. Re-check `FIND_MAX` and rerun the eval once more topics and files exist.
4. Add OCR if scanned PDFs matter.
5. More cost cuts, each checked against the eval: return `FILE_READY` straight after `send_files` (saves one call), shorter history, `TOP_K` 4 to 3, shorter file summaries, Batch API for the first bulk index.
