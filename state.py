import threading
from functools import lru_cache

from store import Store

# one local model serves everyone: the lock makes chat questions and re-indexing wait their turn
lock = threading.Lock()


@lru_cache
def get_store() -> Store:
    return Store()
