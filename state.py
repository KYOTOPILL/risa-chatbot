import threading
from functools import lru_cache

from store import Store

# one local model serves everyone: the lock makes chat questions and re-indexing wait their turn
lock = threading.Lock()


# normalized question -> Reply, only for questions with no history; cleared on every reindex
cache: dict = {}
CACHE_MAX = 500


@lru_cache
def get_store() -> Store:
    return Store()
