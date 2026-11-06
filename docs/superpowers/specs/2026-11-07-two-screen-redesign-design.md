# RiSA Redesign: One Login, Researcher Home and Staff Workspace

Status: DRAFT for approval. Mockups: `.superpowers/brainstorm/69331-1793988822/content/researcher-home.html` and `.superpowers/brainstorm/69803-1793988863/content/staff-workspace.html`.

## Intent and why

The app has three pages split by tool: `index.html` (chat), `track.html` (tracking and document check), `admin.html` (knowledge files). A person has to know which tool they need and jump between pages.

The problem statement (repetitive inquiries, manual document verification, delayed feedback, staff hunting for project status) is about people, not tools. A researcher wants to know what to do next. Staff want to know what needs them now. This redesign regroups the existing pages by person. It adds no new features.

## Goals

- A researcher opens one page and sees what they must do now, the progress of each submission, and can ask the chat from the same page.
- Staff open one workspace that starts on the documents waiting for review, with everything else one click away.
- One login page for both roles. The role decides which screen appears.
- Existing behaviour keeps working: Q&A chat, tracking, document check, staff review, knowledge file management.

## Non-goals (decided: restructure first)

- Chat that knows who is asking, or answers about the user's own submissions.
- Per-document condition checklists, rule checks, search or filters, "stuck" flags, notifications, staff reassign.
- LINE. Web only for now.
- Real CMU login. The mock login stays.
- Changing the knowledge file manager's login. It keeps HTTP Basic auth (decided by the user: the mock login cookie is forgeable and must not guard file deletion).

## Anti-goals (failure even if it works)

- Staff or researchers losing a function they have today.
- A researcher seeing another researcher's submissions.
- Anyone reaching the knowledge file manager with only the mock login.
- Updating a step or reviewing a document taking more clicks than today.

## Decided by the user

- **Researcher home = layout B.** Top: a "สิ่งที่ต้องทำ" list. Below: one stepper card per submission. Chat opens from a 💬 button as a drawer, on any researcher page.
- **Staff workspace = layout A.** Left menu: 📥 รอตรวจ (opens first), 📋 ทุกงาน, 🧩 ประเภททุน, 📁 ไฟล์ความรู้. Row in รอตรวจ shows researcher, submission type, document, AI finding count and a [ตรวจ] button.
- **Web only; restructure existing pages only.**
- **Knowledge files keep Basic auth.** The 📁 menu item opens the existing `/admin` page.

## My calls (change if wrong)

- To-do list content, in order: returned documents with the staff note and a re-upload action, then documents waiting for staff review. Built from data the tracker API already returns.
- Chat drawer calls the existing chat endpoint unchanged and behaves as it does today.
- `/` is the login page, and for a logged-in user it shows their screen. `/track` redirects to `/`. `/admin` stays as the Basic-auth file manager and is linked from the staff menu.
- The standalone public chat page stays reachable at `/chat` with no login, so nothing that links to it breaks. It is not part of the new screens.
- A new researcher with no submissions sees an empty to-do ("ไม่มีงานค้าง") and the chat button.
- Layout works on a phone screen. Researchers will likely use it from phones, and LINE comes later.

## Constraints

- Keep the stack: FastAPI, vanilla JS, Thai UI, no framework, no new dependency. Match the existing style (`style.css`, shared header and look).
- Reuse the existing tracker API (`/api/track/*`) and chat API. Add a backend endpoint only if building the to-do list from existing calls is clearly worse.
- All 209 existing tests stay green. Add route tests for the new `/`, `/chat` and `/track` behaviour.
- No XSS regressions: text goes in with `textContent`, as the current `h()` helper does.
- Update `FRAMEWORK.md` and run `graphify update .` after the code change.

## Left to the builder

- File layout in `web/` (how to split or merge `track.*`, `app.js`, `index.html`) and what to name the new pages. Delete files that become dead.
- Whether the to-do list needs a new endpoint or is derived client-side.
- Visual details: spacing, colours (follow the current look), drawer width, empty and error states.
- Whether staff and researcher screens are two HTML files or one with two views.

## Known gaps (not fixed here)

Mock login is forgeable, no notifications, no staff reassign, no search or stuck flags, chat does not know the user.

## Next

After approval: implementation plan via `superpowers:writing-plans`.
