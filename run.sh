#!/bin/sh
# One command to start RiSA: ./run.sh   (app http://localhost:8000, chat http://localhost:8000/chat)
cd "$(dirname "$0")"
curl -s localhost:11434 >/dev/null || { ollama serve >/tmp/ollama.log 2>&1 & sleep 3; }  # embeddings need Ollama
ollama list | grep -q bge-m3 || ollama pull bge-m3
.venv/bin/python ingest.py >/dev/null 2>&1  # catch up on files changed while the server was off
exec .venv/bin/uvicorn server:app --port 8000
