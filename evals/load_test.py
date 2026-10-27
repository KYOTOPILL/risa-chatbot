"""Concurrent-user timing: python -m evals.load_test --users 5"""
import argparse
import threading
import time

from rag import answer
from store import Store

QUESTION = "ลาพักร้อนได้กี่วันต่อปี"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=3)
    n = ap.parse_args().users
    store, times = Store(), []

    def one() -> None:
        t = time.time()
        answer([], QUESTION, store)  # the app runs questions in parallel too
        times.append(time.time() - t)

    start = time.time()
    threads = [threading.Thread(target=one) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    print(f"users={n} total={time.time() - start:.1f}s per-request={[round(x, 1) for x in sorted(times)]}")


if __name__ == "__main__":
    main()
