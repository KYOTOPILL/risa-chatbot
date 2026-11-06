Is the latest fix to the RiSA office chatbot's file-request search a good fix or not?

## The product
RiSA is an internal Thai-language office chatbot (FastAPI + plain HTML/JS). Staff ask questions about company documents; the bot answers from the documents (RAG: chunk, embed with local bge-m3 through Ollama, store in Chroma, answer with OpenAI gpt-5.4-nano). Staff can also ask for a file ("ขอใบเสร็จค่าครองชีพ", "ขอเอกสารใบเสร็จรับเงินด้วย") and the bot replies with a fixed line plus download links showing the file names. Admins upload, edit and delete files often; the user expects about 500 documents in the future. Only files in a folder named `shareable` are downloadable. The user said folders will be "topics, and the files related to that topic are inside it". Today there is one topic folder (CMU Presidential Scholarship) with 7 downloadable PDFs: 6 near-identical blank receipt forms (Living Allowance, Book and Stationery, Settlement Allowance, Travel to CMU, Travel to Hometown, Thesis Publication) and one 24-chunk Thai announcement PDF. File names are English; user requests are Thai.

## How file requests work now (before the fix)
- A cheap LLM "intent" step decides `wants_file`, `wants_all` and a `category` (topic folder) guess. The small model is unreliable, so a regex also forces wants_file when a request verb (ขอ, ส่ง, โหลด) appears with a document word (ไฟล์, เอกสาร, ใบเสร็จ, ฟอร์ม ...).
- A separate "name index" holds one entry per downloadable file: the file name plus a Thai summary and Thai keywords that gpt-5.4-nano writes once when a file is new or changed (cost measured: about 2,500 input and 280 output tokens for the largest file, much less for small ones; estimated well under 1 US dollar for 500 files, not verified against current prices).
- File requests search this name index directly, send the best match, or every file within a score tie (NAME_TIE 0.03) of the best, and reject anything above a distance of NAME_MAX 0.45. Both thresholds were tuned on these 7 files only.
- Re-indexing is incremental (size + mtime signature), and changing the entry text format needs the index folder deleted and rebuilt once.

## The latest fix (what is on trial)
Three changes made together after the user suggested using the folder structure as a guide:
1. The topic folder (category) the intent step guessed is now used as a soft filter for file requests: search inside that folder first; if nothing there is under NAME_MAX, fall back to searching all folders.
2. The category was briefly added to the text that is embedded for each name entry. Tests showed it made things worse, because all files in one topic share the same prefix, which blurs them together (a request for the scholarship announcement started returning receipts). It was reverted, so the category is used only as a filter, not as embedded text.
3. The regex of document words was extended with ประกาศ, ระเบียบ, นโยบาย, สัญญา, because "ขอประกาศรับสมัครทุน" ("send the scholarship announcement") was treated as a plain question and returned "not found".

## Evidence from testing (live server, real index of the 7 files, 103 unit tests pass)
- "แล้วขอเอกสารใบเสร็จรับเงินด้วย" returned all 6 receipts.
- Thesis-publication request returned only the thesis receipt. Living-allowance request returned only the living-allowance receipt.
- "ขอเอกสารทุน CMU Presidential" and "ขอประกาศรับสมัครทุน" returned only the announcement.
- "ขอไฟล์ใบลา" (a leave form that does not exist) returned no file, which is correct.
- "ขอไฟล์ทั้งหมดของทุน CMU" returned 6 of the 7 files (the seventh is just outside NAME_MAX).
- With only one topic folder today, the category filter has no practical effect yet; it only changes behaviour once a second topic folder exists, and that was not tested with real multi-topic data. There is a unit test with a fake store showing the filter prefers the picked folder and falls back.
- The model's category guess is sometimes wrong; the fallback exists for that reason.
- No test set of real staff requests exists; the 10 questions in evals/questions.json refer to mock documents that were deleted.
- Not committed yet.

## The question
Is this latest fix good, or not? Judge whether it is sound as built, whether it will hold when the folder count and file count grow toward 500 files in many topics, and what is most likely to go wrong.
