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
