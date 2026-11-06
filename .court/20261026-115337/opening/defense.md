# Defense: the CPU-only qwen3:8b deployment should go ahead

1. **The system is already built and tested.** The case file says "Live evals passed 10/10 on the current setup" and lists a complete stack: "FastAPI backend, html/css/js chat page, Ollama running chat model qwen3:8b and embedding model bge-m3, local index directory, local admin page." The objection is that 10 evals is a small sample. It is still direct evidence that the pipeline works, and a CPU-only server changes speed, not answer quality, because the same model weights and retrieval settings are used.

2. **Local hosting suits sensitive data.** The file says "Documents are HR documents; sensitivity of the data was raised as a concern." Ollama, the embeddings and the index all run on the user's own machine, so nothing goes to a third-party API. A CPU server is the cheaper way to keep that guarantee. The objection is that the concern is unresolved. Self-hosting is the best answer to that concern, and it leaves only access control to fix.

3. **The workload is light and the model is a sensible size.** This is a RAG assistant with "top-k 4" and "chunk size 800", so each prompt carries a few thousand characters of context at most. An 8B model is small enough to run on a CPU server. The objection is that CPU generation is slow. The record gives no latency figures, so the objection is unproven. Concurrent users are "not yet decided", which means load is not known to be high, and an internal HR tool may well have few simultaneous users.

4. **The open items are small and fixable.** The two gaps named are "The admin page currently has no authentication" and "HR contact in config is still a placeholder." Both are quick configuration or code fixes that do not touch the architecture. Specs "not yet decided" mean the server can be sized to the model, which is easier than adapting a model to fixed hardware.

**Concessions.** The admin page must not go live without authentication. The record has no CPU latency measurement, no RAM sizing, and no load estimate. Those must be settled before launch. They are conditions on how the deployment proceeds, not reasons to drop it.
