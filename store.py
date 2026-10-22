from dataclasses import dataclass
from pathlib import Path

import chromadb
import ollama

from config import EMBED_MODEL, INDEX_DIR
from docmeta import DocMeta

COLLECTION = "docs"


def embed(texts: list[str]) -> list[list[float]]:
    return ollama.embed(model=EMBED_MODEL, input=texts)["embeddings"]


@dataclass
class Hit:
    text: str
    doc_id: str
    category: str
    downloadable: bool
    mtime: str
    rel_path: str
    distance: float


class Store:
    def __init__(self, index_dir: Path = INDEX_DIR, embed_fn=embed):
        self._client = chromadb.PersistentClient(path=str(index_dir))
        self._embed = embed_fn
        self._col = self._client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    def replace_all(self, items: list[tuple[DocMeta, list[str]]]) -> None:
        self._client.delete_collection(COLLECTION)
        self._col = self._client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        for meta, chunks in items:
            if not chunks:
                continue
            # file name is embedded with the chunk so name-style queries match; it is never shown to staff
            vectors = self._embed([f"{meta.rel_path}\n{c}" for c in chunks])
            self._col.add(
                ids=[f"{meta.doc_id}:{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=vectors,
                metadatas=[
                    {"doc_id": meta.doc_id, "category": meta.category, "downloadable": meta.downloadable,
                     "mtime": meta.mtime, "rel_path": meta.rel_path}
                ] * len(chunks),
            )

    def query(self, question: str, k: int, category: str | None = None) -> list[Hit]:
        if self._col.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=self._embed([question]),
            n_results=min(k, self._col.count()),
            where={"category": category} if category else None,
        )
        return [
            Hit(text=doc, distance=dist, **meta)
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def doc_path(self, doc_id: str) -> str | None:
        res = self._col.get(where={"doc_id": doc_id}, limit=1)
        return res["metadatas"][0]["rel_path"] if res["metadatas"] else None
