# Office RAG Chatbot

Local Thai chatbot over office documents. Answers in Thai from the indexed documents only, says "not found" plus the HR contact otherwise, and hands over a file only when asked and only if it is marked downloadable.

Design: `docs/superpowers/specs/`. Plan: `docs/superpowers/plans/`.

## Setup
1. Install [Ollama](https://ollama.com), then:
   ```
   ollama pull bge-m3
   ollama pull qwen3:8b      # or the newest Qwen instruct ~8B tag; set CHAT_MODEL in config.py to match `ollama list`
   ```
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

## Content folder
Put **only documents every staff member may see** in `content/` (path set by `CONTENT_DIR` in `config.py`). Never put salary, management, or other restricted files there: the bot trusts this folder completely.

- Category = first-level subfolder name (`policy/`, `forms/`, `projects/`). Top-level files are `general`.
- A file is downloadable on request only if a folder in its path is named `shareable` (for example `forms/shareable/expense-claim.pdf`). Everything else is answer-only.
- Supported: PDF, DOCX, TXT, Markdown. Others are skipped with a warning. Scanned (image-only) PDFs are skipped: there is no OCR.
- `python scripts/make_mock_content.py` regenerates the mock documents.

## Run
```
.venv/bin/python ingest.py          # build or refresh the index (re-run after files change)
.venv/bin/streamlit run app.py      # chat page
```
Server later: same code, add `--server.address 0.0.0.0` to expose on the office LAN. Change models in `config.py` (`CHAT_MODEL`, `EMBED_MODEL`) and the HR contact in `HR_CONTACT` (placeholder now).

## Check correctness
```
.venv/bin/pytest                          # unit tests, no Ollama needed
.venv/bin/python -m evals.run_eval        # live question set, needs Ollama + ingest
.venv/bin/python -m evals.load_test --users 5
```
Tuning knobs in `config.py`: `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MAX_DISTANCE`.

## Notes
- PDF extraction uses `pymupdf` (AGPL, fine for internal use); it read Thai from the mock PDF. Re-check with the real Thai files.
- Not yet verified against real models: eval results, tuned thresholds, Thai answer quality, and multi-user latency. Run the evals and load test once Ollama is installed, then record the final values here.
