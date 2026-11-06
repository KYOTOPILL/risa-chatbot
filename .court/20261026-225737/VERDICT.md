# The verdict: NOT GUILTY, 9 to 3

**The case:** Is the latest fix to the RiSA office chatbot's file-request search a good fix or not?

**The charge:** The case fails as stated: it should not go ahead the way it is described.

## How the jury voted

| Juror | Vote | Why |
|---|---|---|
| The Accountant | NOT GUILTY | The change costs nothing to run (no index rebuild, no new model calls), is a no-op with one topic folder, and is uncommitted and easy to revert, so the downside is small even though its benefit is unproven. |
| The First-Time Customer | NOT GUILTY | As someone asking this bot for a file this week, I get the right receipt, the right announcement, and no file for a form that does not exist, and the untested folder filter does nothing yet, so it cannot make my experience worse than it is today. |
| The Competitor | NOT GUILTY | As a rival I would copy the cheap name-index search and ignore this fix, because it is a small, uncommitted, reversible change whose live results are good and whose only risk is a filter that does nothing until a second folder exists. |
| The Retired Judge | GUILTY | The regex fix is proven, but the headline category filter rests on hope, because nothing in the record shows it helping and its own design lets a weak in-folder hit beat a better match elsewhere. |
| The Teenager | NOT GUILTY | Staff only care that asking for a file gets them the right file, and it does that now, so the fix is boring but it works and nobody will notice the filter doing nothing. |
| The Engineer | GUILTY | As an engineer I would not ship a filter that cannot be exercised today and that returns a weak in-folder hit instead of falling back when the model's admittedly unreliable category guess is wrong, with thresholds fitted to 7 files and no real request set to catch regressions. |
| The Small-Business Owner | NOT GUILTY | It's a small, uncommitted, easy-to-undo change that does nothing harmful in a one-folder office today, and the real gaps (no staff request log, no multi-topic test) are cheap to close by watching real use after release, so I wouldn't hold it up. |
| The Statistician | NOT GUILTY | The evidence is thin (7 files, one topic, no real requests), but that is a reason to measure after release rather than to block a small, uncommitted change that cannot alter behaviour in a one-folder setup and can be reverted. |
| The Parent | NOT GUILTY | This is an internal office bot that sends blank forms, so a wrong file costs staff a few minutes and nothing worse, and the change is uncommitted, easy to undo, and can't hurt the one-folder setup we have today. |
| The Investor | NOT GUILTY | As an investor I would back this because the downside is tiny (a small, uncommitted, reversible change that is a no-op in a one-folder setup) and it fixes a failure that was actually observed, even though the filter's real upside is unproven. |
| The Designer | GUILTY | A stranger would ask what this change does today, and the honest answer is nothing you can see, because the main piece (the folder filter) has never run against more than one folder, so I can't call it a good fix as described. |
| The Lawyer | NOT GUILTY | As a lawyer I see no new legal or liability exposure created by this fix, because downloads stay limited to the `shareable` folder, the files are blank internal forms and an announcement, and the filter can only narrow a search that already applied the same cutoff. |

## Charges that stuck
1. The folder filter has never run on real data with more than one topic folder (11 of 12 jurors leaned on this).
2. If the model guesses the wrong folder and that folder holds a weak match under the 0.45 cutoff, the bot sends that wrong file and never checks other folders (all 12 named it, as a reason or as what would change their vote).
3. There is no set of real staff requests to catch regressions, and the thresholds were tuned on 7 files (3 jurors).

## What the defense got right
1. The harmful change (putting the folder name in the embedded text) was tested and reverted, so no index rebuild is needed and nothing embedded has changed.
2. The change is uncommitted, easy to undo, and does nothing with one folder. The record shows no case where it does worse than before. The new regex words also fixed a real "not found" failure, and downloads still stay inside `shareable`.

## Conditions for acquittal
1. Add a second real topic folder and test requests where the folder guess is wrong and the wrong folder has a passing weak match. Show the right file still comes back (most jurors named this).
2. Make the fallback compare against the best score across all folders, not just the 0.45 cutoff, then re-run the test above.
3. Collect 15 to 20 real staff requests, including questions with ประกาศ or นโยบาย that are not file requests, and log which files get sent. Check that `shareable` holds no confidential contracts or regulations.

## The sentence
The court finds no reason to block you, but the main part of this change is unproven. Commit the regex fix now. This week, build the two-folder test and tighten the fallback before you rely on the filter. Keep a request log from day one, so the next change is judged on evidence.

_The full trial is in /Users/kyotopill/Library/CloudStorage/OneDrive-Personal/Desktop/Korkor/Freelance/RiSA Chatbot/.court/20261026-225737: the opening statements, the rebuttals and every juror's vote._

_Made with [/court](https://github.com/alexyc9381/court-skill), a free Claude Code skill by Alex Chen ([@nocodealex](https://instagram.com/nocodealex))._
