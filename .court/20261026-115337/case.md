Deploy the RiSA HR chatbot on a CPU-only server with qwen3:8b

Facts given by the user:
- RiSA Chatbot is a RAG chatbot answering HR policy questions (leave policy, travel allowance, scholarship, forms) for employees, mostly in Thai.
- Stack: FastAPI backend, html/css/js chat page, Ollama running chat model qwen3:8b and embedding model bge-m3, local index directory, local admin page to upload/delete documents and re-index.
- RAG settings: chunk size 800, overlap 100, top-k 4, max cosine distance 0.6. Live evals passed 10/10 on the current setup.
- Proposed deployment target: a server with no GPU (CPU only). Server specs (cores, RAM) and number of concurrent users are not yet decided.
- The admin page currently has no authentication. HR contact in config is still a placeholder.
- Documents are HR documents; sensitivity of the data was raised as a concern.
