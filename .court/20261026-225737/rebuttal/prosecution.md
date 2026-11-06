1. Partly survives. Reverting the embedding change was good practice. But it was caught only because 7 files made the blur visible. The same prefix problem shows up in other places at 500 files, and nothing tests those.

2. Does not survive as "fails safe". The fallback triggers only when nothing in the picked folder is under NAME_MAX. A wrong guess whose folder holds a weak but passing match returns the wrong file and never falls back. The record has no test of that case. The unit test uses a fake store, and the category guess is admitted to be "sometimes wrong".

3. Survives in part. The observed failure is real. But the record only shows the request verb requirement as a safeguard, not any test of false positives. ประกาศ and นโยบาย are also common words in ordinary questions ("ประกาศนี้บอกว่าอะไร"). Whether a verb plus a document word turns a question into a file request is untested.

4. Survives as far as it goes, but it proves little. All 7 files, both thresholds and every test come from one topic. The "all of topic" request already missed 1 of 7, and NAME_MAX 0.45 and NAME_TIE 0.03 were tuned on those same files. That is fitting to the test set, not a measurement.

5. Mostly survives on reversibility. But the point that it is "small" ignores that the change does nothing today. Real use will hit it only when a second topic folder arrives, and that is exactly the untested case. There are also no real staff requests to measure against.

Point for the jury: point 2, whether the soft filter really fails safe when the category guess is wrong and the wrong folder still has a passing match.
