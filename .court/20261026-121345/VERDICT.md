# The verdict: GUILTY, 12 to 0

**The case:** Check the quality of my RAG chatbot framework (RiSA HR chatbot): is it good enough to rely on for answering employees' HR questions?

**The charge:** The case fails as stated: it should not go ahead the way it is described.

## How the jury voted

| Juror | Vote | Why |
|---|---|---|
| The Accountant | GUILTY | I follow the money, and the only number offered to justify relying on this bot for employees' leave and allowance answers is ten questions, with no cost, latency or error-rate figure behind it, so "as described" is not good enough to rely on. |
| The First-Time Customer | GUILTY | As an employee I would not trust this with my leave or money questions this week, because it is not deployable as described and nothing shows it answers correctly beyond ten questions. |
| The Competitor | GUILTY | As a rival I would ignore this today, because a bot with an open admin page, a dead fallback address and 10 evals is a prototype, not something staff can rely on, and I would only worry once those gaps are closed. |
| The Retired Judge | GUILTY | The claim is "good enough to rely on", and the only proof offered is ten passing questions, with no record of what they cover, so that is hope and not evidence. |
| The Teenager | GUILTY | If it's slow or sends me to a fake email on my first try I'm never opening it again, and nobody's checked either, so "rely on it as is" is a no from me. |
| The Engineer | GUILTY | As an engineer I would not rely on it today: the stack is sound and sensibly built, but nothing has been measured (10 evals, no latency, unsized CPU box, unauthenticated admin that can rewrite policy), so "good enough to rely on" is unproven. |
| The Small-Business Owner | GUILTY | I would not open the shop doors on this yet: ten test questions, an unlocked admin page and a dead HR address mean nobody has proven it is safe to hand to employees on Monday morning. |
| The Statistician | GUILTY | Ten passes out of ten questions only rules out a true failure rate above roughly 26% at 95% confidence, so it cannot support relying on this for HR answers, especially with hand-tuned thresholds and no record of which domains or Thai phrasings the questions covered. |
| The Parent | GUILTY | As a parent I would not trust my family's leave days or travel money to a bot that was checked on only ten questions, has an admin page anyone can use to change the policies, and sends people who get no answer to a dead email address. |
| The Investor | GUILTY | I would fund a cheap pilot of this, but not rely on it for HR answers as described, because the upside is modest, the failure cost (wrong money or leave answers) is real, and the only evidence of quality is 10 questions with an open admin page and a dead HR contact. |
| The Designer | GUILTY | A stranger asked "can employees rely on this for HR answers?" would see a dead placeholder contact, an open admin page and ten test questions, and the honest five-second answer is "not yet". |
| The Lawyer | GUILTY | As a lawyer I see an HR bot that may give wrong or superseded leave and money answers with no verified source version, no human fallback (dead hr@example.com), and an open admin page anyone could use to alter policy text, so the company would carry liability for what it tells staff, and the record shows no disclaimer, access control or audit trail. |

## Charges that stuck
1. Ten test questions are too few to prove the bot answers HR questions correctly: 10 jurors.
2. The admin page has no login and the fallback contact is the fake hr@example.com, so it cannot go to employees yet (the defense admitted both): 9 jurors.
3. Nobody has measured how fast it replies, and the server (possibly CPU-only) has not been sized: 5 jurors.

## What the defense got right
1. The stack and design suit the job: local models keep HR files in-house, bge-m3 handles Thai, and guards (distance cutoff, NOT_FOUND marker) favour "ask HR" over guessing. Even the jurors called it sound.
2. The weak spots are known, named and cheap to fix. None needs a redesign, so the verdict is "not yet", not "never".

## Conditions for acquittal
1. Write a bigger test set this week (50 or more Thai questions, written without looking at your tuning), covering leave, travel, scholarship and forms, plus questions with no answer. Report the wrong-answer and refusal rates.
2. Close the two blockers: put a login on the admin page and set a real HR_CONTACT.
3. Measure reply time on the real server, and confirm the index holds only current policy (2026 allowance, the new scholarship PDF).

## The sentence
The court finds the project is a promising prototype, not yet something staff can rely on. Do not put it in front of employees as described. Fix the login and contact today, build the larger test set, time it on the real machine, then come back. Run it as a small pilot until the numbers are in.

_The full trial is in /Users/kyotopill/Library/CloudStorage/OneDrive-Personal/Desktop/Korkor/Freelance/RiSA Chatbot/.court/20261026-121345: the opening statements, the rebuttals and every juror's vote._

_Made with [/court](https://github.com/alexyc9381/court-skill), a free Claude Code skill by Alex Chen ([@nocodealex](https://instagram.com/nocodealex))._
