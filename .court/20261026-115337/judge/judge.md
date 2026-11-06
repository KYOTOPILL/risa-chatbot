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
