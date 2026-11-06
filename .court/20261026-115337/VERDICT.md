# The verdict: GUILTY, 6 to 0

**The case:** Deploy the RiSA HR chatbot on a CPU-only server with qwen3:8b

**The charge:** The case fails as stated: it should not go ahead the way it is described.

## How the jury voted

| Juror | Vote | Why |
|---|---|---|
| The Teenager | GUILTY | If the bot makes me stare at a spinner for ages on some mystery server nobody has even sized yet, I'm going back to just asking HR, and nobody's coming back next week. |
| The Statistician | GUILTY | A 10-question eval is too small to estimate real accuracy, and with no latency, hardware or user-count data, "deploy as described" asks us to approve a plan whose key unknowns are all unmeasured, and plans committed to before such measurement often miss on capacity. |
| The Parent | GUILTY | As a parent I would not hand my family's HR records and leave answers to a system where anyone on the network can delete or swap the policy documents, and where nobody has measured whether it even answers in time. |
| The Small-Business Owner | GUILTY | I would not sign off on buying and running a server when nobody has decided its size, who will use it, or how fast it answers, and the open front door on the admin page means the first slow month could also be the month someone wipes the leave policy. |
| The Retired Judge | GUILTY | The case asks for approval of a CPU-only 8B deployment when the record holds no latency figure, no hardware spec and no user count, and the defense carries the burden of showing it works but offers only hope that the missing facts will turn out well. |
| The Competitor | GUILTY | As a rival selling a hosted Thai HR assistant, I would simply ignore a slow CPU-only 8B bot with an open admin page that has never been timed, because it would sink itself on day-one latency and trust. |

## Charges that stuck
- No measured answer time for Thai questions on a CPU-only 8B model: 6 of 6 jurors.
- Server size and number of users are undecided, so nobody knows if it can cope: 6 of 6 jurors.
- The admin page has no login, so anyone who reaches it could delete or swap HR documents: 5 of 6 jurors.

## What the defense got right
- The fixes are small: an admin login (or closed network) and a real HR contact are quick edits, not a redesign.
- Running everything locally keeps sensitive HR data away from outside services, and 10/10 shows the pipeline works.

## Conditions for acquittal
1. Write down the server's cores, RAM and expected user count, then time Thai questions on that machine at that load and show acceptable answer times.
2. Put the admin page behind a login or a closed network, and replace the placeholder HR contact.
3. Grow the eval set from 10 to a few hundred Thai questions and show an acceptable pass rate.

## The sentence
The court does not stop the project, but it will not let it launch as described. This week, decide the server size and user count, time real Thai questions on that machine, and lock the admin page. Come back with the numbers. If answers are too slow, change the hardware or the model.

_The full trial is in /Users/kyotopill/Library/CloudStorage/OneDrive-Personal/Desktop/Korkor/Freelance/RiSA Chatbot/.court/20261026-115337: the opening statements, the rebuttals and every juror's vote._

_Made with [/court](https://github.com/alexyc9381/court-skill), a free Claude Code skill by Alex Chen ([@nocodealex](https://instagram.com/nocodealex))._
