# Office RAG Chatbot: Design

## Intent and why

Staff keep asking HR the same policy questions, ask HR for documents, and ask for progress on work. HR time goes to repeat answers. This project builds a chatbot that staff open in a browser and ask in plain language. It answers from the office's own documents using retrieval-augmented generation (RAG).

Three kinds of question must work:

1. **Policy questions** ("how many leave days do I get?"). Answer from policy documents.
2. **Document requests** ("I need the expense claim form"). Give the file as a download if it is downloadable. Never show where it is stored.
3. **Progress questions** ("what is the status of project X?"). Answer from status or report documents that exist in the content folder. The bot does not connect to live project tools.

Success: staff get a correct answer in seconds for common questions, and HR gets fewer repeat questions.

## Goals

- Chat page in a web browser for all staff.
- Answers come only from the indexed documents, and answers do not show file names. The builder logs the source file(s) of each answer for debugging (not visible to staff).
- When no source supports an answer, the bot says it did not find one. It does not guess.
- English and Thai, mixed, in questions and documents. Answers are in Thai only.
- Runs fully local with free and open-source models. No data leaves the machine.
- First on the owner's Mac, later on a local office server, with the same code.

## Non-goals

- No per-user login or per-user permissions.
- No live connection to project tools, Drive APIs, or HR systems.
- No automatic sync from the drive. Re-indexing is a manual script run.
- No document editing, form filling, or actions. Read-only Q&A.

## Anti-goals

- The bot must never expose a restricted document (salary, management). The guard is the content folder: only documents every staff member may see are placed in it. The bot trusts that folder completely, so keeping restricted files out of it is the owner's responsibility.
- A confident wrong answer is worse than "not found". Strict grounding beats helpfulness.

## Constraints

- Free and open-source models only.
- Owner's dev machine is a Mac with 16GB RAM.
- Final deployment is a local server of unknown specs.
- Documents live in a drive. Assumed to be synced to a local folder that the ingest script reads. Which drive product is not confirmed.

## Decisions made by the owner

- Open-source models, run locally.
- Mac first, local server later.
- Staff language is English and Thai mixed.
- Only everyone-can-see documents go into the database. No access control inside the bot.

- Mac has 16GB RAM. The 8B model plan stands.
- Corpus is assumed to be 100+ files. No sample files exist yet.
- Staff cannot search by file name or path. The bot never shows storage paths. It may offer the matching document as a download when asked. Correct answers matter more than locating files.
- Answers are Thai only. Follow-up questions are supported. Multiple users are possible.
- HR contact details are mock-up placeholders for now (see calls below).

## Calls made by the designer (owner may override)

- **Sample files:** none yet. The first build step is an ingestion spike on a small set of mock files, including Thai PDFs. Real files replace them when the owner has them.
- **HR contact:** one placeholder string in a config file (for example "HR team, hr@example.com"). The owner swaps in the real contact later.
- **Correctness checks:** because correctness is the top priority, the builder provides a small question set with expected answers and source files, and a script that runs it and reports passes and failures.

- **Language:** Python.
- **Model runner:** Ollama.
- **Chat model:** a Qwen instruct model, about 8B parameters on the Mac. Chosen for Thai and English ability and for following "answer only from sources". A larger size on the server is a model-name change. Confirm the newest Qwen tag in Ollama's library when building.
- **Embeddings:** `bge-m3` through Ollama (multilingual).
- **Vector store:** Chroma, persisted to a local folder.
- **UI:** Streamlit single page chat.
- **Ingest:** a script that walks the content folder, extracts text from PDF, DOCX, and plain text/Markdown, splits into chunks, embeds, and stores them with file name metadata. Re-running refreshes the index.
- **Answering:** retrieve the top few chunks, give them to the model with an instruction to answer only from them. No file names or citations appear under the answer. If retrieval returns nothing relevant, reply that nothing was found and suggest asking HR.
- **Progress questions** are handled by the same pipeline. Their answers are only as current as the status documents in the folder, and the answer states the document's date (modified date) when it reports progress, so staff can see how current it is.

- **File names and paths are indexed as searchable text**, so "where is the expense form?" works even when the form has little text.
- **File modified date is stored.** When sources conflict, prefer the newest and say so in the answer.
- **Multi-turn chat.** Follow-up questions work ("and for part-time staff?"). Each browser session keeps its own history. Before retrieval, the bot rewrites a follow-up into a standalone question using recent history. Sessions never see each other's history.
- **Answers are in Thai**, even when the question or the source document is English. Specific English words (names, product or system names, technical terms, acronyms) may be mixed into the Thai sentence. Full English sentences are not allowed.
- **Multiple users at once.** Each user has a separate session. Requests share one local model, so concurrent requests wait in a simple queue. Builder measures response time with several users on the Mac and reports it. The server phase binds to the office LAN.
- **Document delivery:** staff do not browse or search file names or paths. When a user asks for a document ("I need the expense claim form"), the bot finds the right one by meaning and gives the file itself as a download in the chat. When a user only asks for information, the bot answers in text and gives no file. The product is a chatbot only: no file browser, no file list, no direct file links. A file is downloadable only if the owner marked it downloadable. My call on how: a file is downloadable if any folder in its path is named `shareable` (for example `forms/shareable/expense-claim.pdf`). Those files are indexed and downloadable on request. All other files are indexed for answers only. **Categories:** a document's category is the name of its first-level subfolder in the content folder (for example `policy`, `forms`, `projects`). The `shareable` folder name is ignored for category. Category is stored as metadata and used to filter or boost retrieval. When a question is unclear, the bot may ask which area the user means. Files at the top level have category `general`. If a user asks for a non-downloadable document, the bot answers from its content if it can and says it cannot send the file. The download is served by the chat app through an allow-list of `shareable` files, never by path.
- **No graph (GraphRAG) in v1.** Revisit only if the correctness test set shows questions that span many documents failing. If several documents could match, the bot asks the user which one they mean.
- **Formats:** PDF, DOCX, TXT, Markdown. XLSX and PPTX only if the sample files show they are needed.

## Known risks

- Thai PDFs sometimes extract as garbled text. Test with real Thai files early, before building anything around ingestion.
- Small open models hallucinate more than large hosted models. Strict grounding prompt, a relevance threshold, and the correctness test script are the mitigation. Staff cannot see sources, so wrong answers are harder for them to spot.
- Stale documents give stale answers, especially for progress questions.

## Left to the builder

- Chunk size and overlap, number of retrieved chunks, relevance threshold. Tune on real documents.
- Exact prompt wording.
- Project layout, dependency pinning, and README.
- How to extract text from scanned (image-only) PDFs. Out of scope unless real files need it. If they do, report back before adding OCR.
- A small set of example question/answer checks the owner can run to see the bot works.
