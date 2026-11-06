VOTE: NOT GUILTY
REASON: The change costs nothing to run (no index rebuild, no new model calls), is a no-op with one topic folder, and is uncommitted and easy to revert, so the downside is small even though its benefit is unproven.
DECIDING FACT: The category embedding that would have forced an index rebuild and re-spend was reverted, so the remaining fix adds no indexing cost and does not change what is embedded.
WOULD FLIP IF: A multi-topic test showed the folder filter returning a wrong file where the old search across all folders would have returned the right one, or the record showed a real cost, such as a forced index rebuild, attached to shipping it.
