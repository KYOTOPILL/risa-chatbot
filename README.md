# Office RAG Chatbot

Local Thai chatbot over office documents. Design: `docs/superpowers/specs/`. Plan: `docs/superpowers/plans/`.

## PDF extraction choice
`pymupdf` (AGPL, fine for internal use) extracts Thai from the mock PDF; `pypdf` also did. `pymupdf` chosen as more robust on real-world PDFs. Re-check with the real Thai files.
