# Defense

1. **The framework has been hardened by real failures.** The record lists fixes for "stale collection, atomic reingest, file-request margin, qwen think handling, logging, UI errors", then "mapping of Thai private-use glyphs from PDFs; deduplication of overlapping chunks". These are bugs found by running the system on actual Thai documents, and each one is closed. The objection is that a fix history shows fragility. But the fixes are specific and the problem classes are gone, which is what a maturing system looks like.

2. **It is built to refuse rather than guess.** Hits farther than "MAX_DISTANCE 0.6" are dropped, a "NOT_FOUND marker" exists, files are offered "only if within 0.15 of best hit", and replies must clear "THAI_MIN_RATIO 0.5". For HR, a wrong answer is worse than "ask HR", so abstention guards matter most. The objection is that the constants are hand-tuned. Yes, but they are visible in one config.py and tunable. Hidden defaults would be worse.

3. **There is passing evidence, and the tests are sound.** "live evals passed 10/10", run against the live stack, not mocks. Unit tests "no longer depend on content/", so they stay valid while policy files change. Ten questions is small, and I concede that. It still shows the core path of retrieve, answer and decline works end to end. It is a reason to grow the set, not to stop.

4. **The stack suits the use case.** Local Ollama with bge-m3 (multilingual embeddings, relevant for Thai) and qwen3:8b keeps HR documents on the organisation's own machine. The admin page lets HR upload, delete and re-index without a developer. The architecture is plain Python, FastAPI and static html, so it is cheap to maintain and fix. The objection is the unsized, possibly CPU-only server. That is a deployment sizing task and has no bearing on answer quality. The record gives no latency figure, so the risk is unmeasured, not shown to be real.

5. **The gaps are small, known and fixable.** The record names them: no admin authentication, a placeholder "hr@example.com", no latency measurement. All are a day's work or less, none touches retrieval design, and the build lists them honestly. "Go ahead as described" can mean proceeding with these as pre-launch gates.

**Conceded:** the unauthenticated admin page cannot ship to employees as it stands. The placeholder HR contact would send users to a dead address. Neither can be defended; both are blockers to fix, not grounds to stop.
