1. Partly survives. Ten questions is thin and the record does not say what they cover, but 10/10 live passes after fixes is real evidence the pipeline works end to end. The "25% or more" figure and "tuned in the same commit series" are inference, since the record shows no overlap between eval questions and fixes.

2. Mostly fails. Hand-set constants are normal for a small corpus, and the record shows they were revised after evidence (TOP_K moved to 4, chunk dedupe, glyph mapping). The Thai-ratio admission is honest and low risk. A dropped chunk producing NOT_FOUND is a safe failure by design.

3. Partly survives. The deleted and untracked files are a local working-tree state, not a statement about the index. The record is silent on index contents, so this is an open check, not a defect. Atomic reingest and the stale-collection fix show the author handles index drift.

4. Survives, but only for deployment. The record admits no admin auth and a placeholder HR_CONTACT. Both are small, known, fixable before launch. They do not touch answer quality, which is what was asked.

5. Survives as a gap, not a flaw. Latency is unmeasured, so neither side can claim a figure. It is a one-hour measurement.

The point for the jury: point 1. The question is whether the bot is good enough to rely on for answers, and only the eval evidence speaks to that. If ten passes plus the fix history show it answers correctly or declines safely, points 2 to 5 are pre-launch checklist items, not grounds to stop.
