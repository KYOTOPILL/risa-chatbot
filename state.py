import threading
from functools import lru_cache

from store import Store

# one re-index at a time; chat never waits for it (each question runs in its own thread, the model servers queue themselves)
lock = threading.Lock()


# normalized question -> Reply, only for questions with no history; cleared on every reindex
cache: dict = {}
CACHE_MAX = 500


@lru_cache
def get_store() -> Store:
    return Store()
