# RiSA: how the framework works

RiSA is a Thai-language chatbot that answers staff questions from company documents and sends the files they ask for.
Stack: FastAPI + plain HTML/JS, Chroma vector store, local `bge-m3` embeddings (Ollama), chat model `gpt-5.4-nano` via OpenAI by default; `RISA_CHAT_BASE_URL` + `RISA_CHAT_MODEL` point it at any OpenAI-compatible server (e.g. local Ollama `qwen3:8b`).

## 1. The big picture

```
 content/<topic>/...            (admin uploads, edits, deletes files)
        |
        v
  ingest.build_index  --->  Store (Chroma)
   - extract text (+xlsx,pptx) - "docs"  collection: text chunks     (for answering questions)
   - chunk 800/100            - "names" collection: one entry per   (for finding files)
   - embed (bge-m3)             downloadable file = name + Thai summary
   - LLM summary (new files)
        |
        v
  rag.answer(history, message, store)
   LLM + 4 tools  ->  Reply(text, file_doc_ids, sources)
        |
        v
  server.py  /api/chat  ->  web/app.js shows text + file names as download links
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
| `AGENT_SYSTEM` | System prompt: tool descriptions, Thai-only, tool results are data, reply `NOT_FOUND` when nothing fits, `OUT_OF_SCOPE` when the question has nothing to do with the company (weather, recipes, coding). |
| `TOOLS` | The four tool definitions below. |
| `_dedupe`, `_context` | Drop overlapping chunks and format search results with their modified date. |
| `is_mostly_thai` | Detects an English reply so it can be retried once in Thai. |
| `Reply`, `Turn` | Result and history dataclasses. |
| `usage` | Running totals of calls, prompt tokens and completion tokens, filled by `_post` from OpenAI's `usage` field. `evals/run_eval.py` prints it. |
| `MAX_ANSWER_TOKENS` | Output cap (600) sent as `max_completion_tokens` by `chat_tools`. Summaries use `chat()` and are not capped. |

The four tools:

| Tool | When the model uses it | What it returns |
|---|---|---|
| `search_documents(query, topic?)` | Questions about what documents say | Up to `TOP_K=4` chunks, fenced in `<context>`, hits over `MAX_DISTANCE=0.6` dropped |
| `find_files(query, topic?)` | User asks for or asks about a file | Up to `FIND_K=8` candidates as `f1 \| name \| topic \| summary` |
| `send_files(file_ids)` | After `find_files`, to attach files | Confirmation. Only ids from this turn's `find_files` are accepted |
| `list_topics()` | Vague "what documents do you have" | Topic folders with file counts, so the bot asks which topic |

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
| `Store.topics()`, `categories()` | Topic folders and how many downloadable files each has. |
| `Store.doc_path()` | Maps an id to a path. The server uses it to show file names. |
| `Store.cached_summary(sig)`, `remember_summary(sig, text)` | Summaries remembered by file signature (size + mtime) in `index/summaries.json`. Moving or renaming a file, or switching downloadable off and on, keeps the same content, so it keeps its summary and costs no new API call. `ingest.build_index` reads this before calling the LLM, and `/api/admin/files` falls back to it so a non-downloadable file still shows its description. |
| `Store.summaries(ids=None)` | doc_id to Thai summary for downloadable files. Used by `/api/chat` (file cards) and `/api/admin/files`. |
| `NameHit` | Result row for file search. |

### `ingest.py` and `docmeta.py` (the intake)

- `build_index(content_dir, store, summarize)` walks `content/`, skips files whose signature is unchanged, and returns `{"indexed","changed","skipped"}`.
- `summarize(text)` asks the model for a Thai summary once for every new or changed file, downloadable or not, and remembers it by file signature, so a description never depends on the downloadable switch. A file whose summary is missing (for example indexed before this rule, or a failed call) is indexed again on the next reindex. Only downloadable files' summaries go into the name index used by file requests. A failure is logged and the file is still indexed.
- `DocMeta` gained `summary` and `sig`.
- `extract.py`: `extract_text` reads PDF (pymupdf), DOCX, XLSX (`_xlsx`), PPTX (`_pptx`), TXT and MD. `_xlsx` writes one paragraph per row as `[Sheet] Header: value | Header: value` (first non-empty row is the header, empty rows and cells are skipped, at most `MAX_SHEET_ROWS=3000` rows per sheet, cached formula values), so chunking never cuts a row and each value keeps its column name. `_pptx` writes one paragraph per slide: text boxes, tables (cells joined by ` | `), grouped shapes and speaker notes; slides with no text are skipped. Old `.xls` and `.ppt` are not supported (`SUPPORTED_EXTS` in `config.py`, also the upload picker in `admin.html`). New dependencies: `openpyxl`, `python-pptx`.

### Other files

- `server.py`: `/api/chat` returns `{"text", "files": [{"id","name"}]}`. A question with no history is looked up in `state.cache` (key: lower-cased, whitespace-normalized message) before any OpenAI call.
- `state.py`: `cache` (up to `CACHE_MAX=500` replies, no expiry) is cleared by `admin.reindex`, so a changed index never serves old answers. Questions with history are never cached, and failed answers are never cached.
- `web/icons.js`: `fileIcon(name)` returns an inline SVG icon (page with folded corner and a coloured label: PDF, DOC, XLS, PPT, TXT, or the upper-cased extension in grey) that `app.js` appends at the end of each file link. Edit `TYPES` and `COLORS` in `icons.js` to change labels or colours; size is the `.ftype svg` rule in `style.css`.
- Chat screen (`web/app.js`, `style.css`): each reply is a row with a bot avatar (RiSA), the bubble and a time stamp shown on hover (not restored after a refresh). Each file is a card (`.fcard`): type icon, name (2 lines max), Thai summary (2 lines max), `TYPE · size`, download arrow. While waiting, the status text rotates through `WAITING` (it is not tied to the real tool step: that needs streaming). Old behaviour kept: renders each file as a link, and saves sent file names in history so "the other one" works.
- `admin.py`: reindex calls `build_index(..., summarize)`. Debounce lives here: every successful upload, replace, delete, move, folder rename or folder delete (the `CHANGES` dependency) restarts a `REINDEX_DELAY` (2.5 s) timer that runs `reindex()`, so the index catches up even when the browser tab is closed. `GET /api/admin/index-status` returns `{state: ok|stale|busy|error, indexed, skipped, error}`; the admin page polls it every 1.5 s while stale or busy. A failed run shows `error` and the next change retries. `/api/admin/files` rows now include `summary`.
- File manager (`web/admin.html`, `admin.js`, `admin.css`): breadcrumb, an index status strip (green = chat has the latest files, amber = changes waiting for the automatic reindex, spinner = updating, red = error; no button, it updates by itself; the strip shows the server's status), a selection bar that slides in only when files are ticked, folder rows (count, total size, last edit), file rows (type icon, name with a small `i` button that opens the AI-written Thai summary in a popover, and a `ดาวน์โหลดในแชท` column with an on/off switch that moves the file in or out of the `shareable` folder; the selection bar has `เปิดให้ดาวน์โหลด` / `ปิดการดาวน์โหลด` for many files at once) and a `⋯` menu per row (rename, move, replace, delete in red, with the undo toast). Uploading (button or drag and drop) first opens a dialog: `ให้ดาวน์โหลดผ่านแชทได้` is ticked by default, so new files can be found by file requests; untick it for internal-only documents. The open folder's rename and delete are in a `⋯` menu next to the breadcrumb (same menu as on the folder row). Rows are at least 52 px high. Drag and drop move, double-click rename and the automatic reindex 2.5 s after a change (now timed by the server) are unchanged.
- `config.py`: `CHAT_MODEL` (override with `RISA_CHAT_MODEL`), `SUMMARY_CHARS`.
- `evals/run_eval.py` + `evals/questions.json`: 24 real CMU-based cases. Run with `python -m evals.run_eval` (about 50 API calls).
- `tests/`: 99 tests. `test_rag.py` uses a scripted `FakeLLM` and `FakeStore`, so no network is needed.

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

- Bigger model did not help, so `gpt-5.4-nano` stays.
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
