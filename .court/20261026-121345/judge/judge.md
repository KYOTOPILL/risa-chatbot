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
