1. Partly survives. The live results do not exercise the filter, but they are the regression check for the regex and the search. The filter is also a small, reversible change that cannot hurt a one-folder setup, and a unit test covers prefer and fallback. The record does not show a multi-topic test, and that gap is real.

2. Survives in part. A weak same-folder hit under 0.45 would be returned. But the filter only narrows a search that already applies the same NAME_MAX cutoff over all folders, so a weak hit would also have been available before the fix. The record gives no evidence that the filter makes it likelier. The prosecution's claim that no error is logged is not in the record.

3. Survives as a scaling risk, not as a flaw in this fix. The thresholds predate this change. The filter shrinks the candidate set, which should reduce tie bundles as folders multiply. The record does not say how often ties happen at scale.

4. Does not survive as stated. The regex was already in place and this change only extends it. The case describes the pre-fix miss as a real failure ("ขอประกาศรับสมัครทุน" returned "not found"), and the extension fixed it. The "ส่ง ... นโยบาย" false-positive is the prosecution's guess, with no test or record behind it.

5. Mostly survives on the missing real-request test set, which is a gap in the whole project, not in this change. It does not survive on bundling, because the case says the category embedding was tested, found harmful and reverted before the commit. The cost estimate is flagged in the case as unverified.

The point for the jury: whether the filter is safe to commit without a multi-topic test. The prosecution has not shown it makes results worse than before, and the record does not show it makes them better.
