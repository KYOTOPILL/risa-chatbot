# Defense rebuttal

1. Survives in part. The record confirms no admin authentication, and the damage described is real. But it is a fixable gap, not a flaw in the case. Auth or a network restriction on one page is small work, and the record does not say the admin page would be exposed.

2. Survives as a gap, not as a failure. Specs and user count are undecided, so the case is unfinished, not wrong. The record has no latency numbers, so "tens of seconds" is a guess. Local, private hosting is the likely reason for choosing CPU, and the record is silent on that. A load test would settle it.

3. Partly survives. Ten questions is small, and the record does not say whether they were in Thai or ran on CPU. But the record says the 10/10 followed fixes (commits mention a NOT_FOUND marker and Thai glyph mapping), which suggests the evals were run on purpose. The right answer is more evals, not cancelling the deployment.

4. Does not survive as a reason to stop. A placeholder contact is a one-line config edit and a pre-launch checklist item. It says nothing about whether the design works.

5. Survives only as missing information. The record shows a local index, local models and no cloud service, which keeps the data on the user's own server. That is a point in favour of the case. The absence of a stated logging or backup plan is a to-do, not a defect.

**Decide on point 2.** It is the only point that could make the whole plan unworkable, not merely incomplete. Points 1, 4 and 5 are cheap to fix and point 3 needs more testing.
