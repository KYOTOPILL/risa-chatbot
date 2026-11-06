VOTE: NOT GUILTY
REASON: As a rival I would copy the cheap name-index search and ignore this fix, because it is a small, uncommitted, reversible change whose live results are good and whose only risk is a filter that does nothing until a second folder exists.
DECIDING FACT: The filter is a no-op with one topic folder, and the record shows no evidence it makes results worse than before, while the live checks (single receipt, all 6 receipts, announcement, nonexistent leave form returning nothing) all came out right.
WOULD FLIP IF: A test with two or more real topic folders showed a wrong category guess returning a wrong file from a weak same-folder match under NAME_MAX instead of falling back.
