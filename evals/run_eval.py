"""Correctness check: run evals/questions.json against the real bot. Exit 1 on any failure."""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from config import HR_CONTACT
import rag
from rag import Reply, Turn, answer, is_mostly_thai


@dataclass
class Result:
    q: str
    passed: bool
    reasons: list[str] = field(default_factory=list)


def check(case: dict, reply: Reply, names: list[str] = ()) -> list[str]:
    bad = []
    if not is_mostly_thai(reply.text):
        bad.append("answer is not Thai")
    bad += [f"missing {s!r}" for s in case.get("must_include", []) if s not in reply.text]
    bad += [f"unexpected {s!r}" for s in case.get("must_not_include", []) if s in reply.text]
    if "expect_files" in case:  # each expected name fragment matches one sent file, and nothing else is sent
        left = list(names)
        for frag in case["expect_files"]:
            hit = next((n for n in left if frag.lower() in n.lower()), None)
            if hit is None:
                bad.append(f"missing file {frag!r}")
            else:
                left.remove(hit)
        bad += [f"unexpected file {n!r}" for n in left]
    if "expect_file" in case and case["expect_file"] != bool(reply.file_doc_ids):
        bad.append(f"expect_file={case['expect_file']} got {reply.file_doc_ids}")
    if "expect_not_found" in case and case["expect_not_found"] != (HR_CONTACT in reply.text):
        bad.append(f"expect_not_found={case['expect_not_found']}")
    return bad


def run(cases: list[dict], answer_fn, file_names=lambda ids: ids) -> list[Result]:
    results = []
    for case in cases:
        history = [Turn(**t) for t in case.get("history", [])]
        reply = answer_fn(history, case["q"])
        bad = check(case, reply, file_names(reply.file_doc_ids))
        results.append(Result(case["q"], not bad, bad))
    return results


if __name__ == "__main__":
    from store import Store

    store = Store()
    cases = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    names = lambda ids: [Path(store.doc_path(i)).name for i in ids]
    if len(sys.argv) > 1:  # `run_eval 8`: only 8 evenly spaced cases, to keep API cost down
        n = int(sys.argv[1])
        cases = cases[:: max(1, len(cases) // n)][:n]
    results = run(cases, lambda history, q: answer(history, q, store), names)
    for r in results:
        print("PASS" if r.passed else "FAIL", r.q, *r.reasons, sep="  ")
    print(f"{sum(r.passed for r in results)}/{len(results)} passed")
    print("tokens:", rag.usage)
    sys.exit(0 if all(r.passed for r in results) else 1)
