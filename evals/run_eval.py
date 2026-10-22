"""Correctness check: run evals/questions.json against the real bot. Exit 1 on any failure."""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from config import HR_CONTACT
from rag import Reply, Turn, answer, is_mostly_thai


@dataclass
class Result:
    q: str
    passed: bool
    reasons: list[str] = field(default_factory=list)


def check(case: dict, reply: Reply) -> list[str]:
    bad = []
    if not is_mostly_thai(reply.text):
        bad.append("answer is not Thai")
    bad += [f"missing {s!r}" for s in case.get("must_include", []) if s not in reply.text]
    bad += [f"unexpected {s!r}" for s in case.get("must_not_include", []) if s in reply.text]
    if "expect_file" in case and case["expect_file"] != bool(reply.file_doc_ids):
        bad.append(f"expect_file={case['expect_file']} got {reply.file_doc_ids}")
    if "expect_not_found" in case and case["expect_not_found"] != (HR_CONTACT in reply.text):
        bad.append(f"expect_not_found={case['expect_not_found']}")
    return bad


def run(cases: list[dict], answer_fn) -> list[Result]:
    results = []
    for case in cases:
        history = [Turn(**t) for t in case.get("history", [])]
        bad = check(case, answer_fn(history, case["q"]))
        results.append(Result(case["q"], not bad, bad))
    return results


if __name__ == "__main__":
    from store import Store

    store = Store()
    cases = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    results = run(cases, lambda history, q: answer(history, q, store))
    for r in results:
        print("PASS" if r.passed else "FAIL", r.q, *r.reasons, sep="  ")
    print(f"{sum(r.passed for r in results)}/{len(results)} passed")
    sys.exit(0 if all(r.passed for r in results) else 1)
