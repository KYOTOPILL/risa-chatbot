import threading
import time
from contextlib import contextmanager
from functools import lru_cache

from app.core import config
from app.core.config import TRACKER_DB
from app.rag.store import Store
from tracker import Tracker

# one re-index at a time; chat never waits for it (each question runs in its own thread, the model servers queue themselves)
lock = threading.Lock()


# normalized question -> Reply, only for questions with no history; cleared on every reindex
cache: dict = {}
CACHE_MAX = 500


@lru_cache
def get_store() -> Store:
    return Store()


@lru_cache
def get_tracker() -> Tracker:
    return Tracker(TRACKER_DB)


_busy: dict[str, int] = {}  # ip -> questions being answered right now; entry removed at 0
_busy_lock = threading.Lock()
_starts: dict[str, list[float]] = {}  # key -> start times in the last minute


@contextmanager
def slot(ip: str):  # the key is the user id (server.py)
    """Yield True if this IP may start another question now, else False. No limit on how many it asks over time:
    the page sends one at a time, so only a script flooding the API ever has several in flight."""
    with _busy_lock:
        now = time.time()
        recent = _starts[ip] = [t for t in _starts.get(ip, []) if now - t < 60]
        ok = (not config.MAX_INFLIGHT or _busy.get(ip, 0) < config.MAX_INFLIGHT) and (not config.MAX_PER_MIN or len(recent) < config.MAX_PER_MIN)
        if ok:
            recent.append(now)
            _busy[ip] = _busy.get(ip, 0) + 1
    try:
        yield ok
    finally:
        if ok:
            with _busy_lock:
                _busy[ip] -= 1
                if not _busy[ip]:
                    del _busy[ip]
