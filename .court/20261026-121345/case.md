Check the quality of my RAG chatbot framework (RiSA HR chatbot): is it good enough to rely on for answering employees' HR questions?

Facts from the project and conversation:
- Purpose: answer HR policy questions (leave policy, travel allowance, scholarship, expense claim forms) for employees, mostly in Thai. Can offer downloadable documents.
- Stack: Python, FastAPI backend, plain html/css/js chat page, Ollama running chat model qwen3:8b and embedding model bge-m3, local index directory, local admin page to upload/delete documents and re-index.
- All RAG settings are hardcoded constants in config.py, tuned by hand, not automatic: CHUNK_SIZE 800, CHUNK_OVERLAP 100, TOP_K 4, MAX_DISTANCE 0.6 (cosine, hits farther are dropped), FILE_MARGIN 0.15 (file offered only if within 0.15 of best hit), THAI_MIN_RATIO 0.5 (reply must be at least half Thai characters; the code comment itself notes this lets a half-Thai reply through).
- Quality evidence: live evals passed 10/10 (commit c918d45). Unit tests no longer depend on content/ (commit 18f6720).
- Recent fixes in git history: stale collection, atomic reingest, file-request margin, qwen think handling, logging, UI errors; prompt wording and a NOT_FOUND marker; mapping of Thai private-use glyphs from PDFs; deduplication of overlapping chunks.
- Known gaps: the admin page has no authentication; HR_CONTACT in config is still a placeholder (hr@example.com); the eval set is 10 questions; no measured latency; target server (possibly CPU-only) not sized.
- Working tree: several content files are deleted locally and one new scholarship PDF is untracked.
