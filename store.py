import json
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
import ollama

from config import EMBED_MODEL, INDEX_DIR
from docmeta import DocMeta

COLLECTION = "docs"
NAMES = "names"  # one entry per downloadable file: its name, so file requests never depend on chunk text


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


@dataclass
class NameHit:
    doc_id: str
    rel_path: str
    distance: float
    category: str = ""
    summary: str = ""


def display_summary(text: str) -> str:
    """The Thai sentences of a summary; the keyword list after it is for search, not for display."""
    return re.split(r"\n\n|คำค้น:", text)[0].strip()


class Store:
    def __init__(self, index_dir: Path = INDEX_DIR, embed_fn=embed):
        self._client = chromadb.PersistentClient(path=str(index_dir))
        self._embed = embed_fn
        self._summary_file = Path(index_dir) / "summaries.json"

    # Summaries are remembered by file signature (size + mtime), not by path: moving or renaming a file, or
    # switching downloadable off and on, keeps the same content, so it keeps its summary and costs no new API call.
    def cached_summary(self, sig: str) -> str:
        try:
            return json.loads(self._summary_file.read_text(encoding="utf-8")).get(sig, "")
        except (OSError, ValueError):
            return ""

    def remember_summary(self, sig: str, summary: str) -> None:
        try:
            data = json.loads(self._summary_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data[sig] = summary
        tmp = self._summary_file.with_suffix(".part")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._summary_file)

    @property
    def _col(self):
        # looked up each time: another process (ingest) may have replaced the collection
        return self._client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    @property
    def _names(self):
        return self._client.get_or_create_collection(NAMES, metadata={"hnsw:space": "cosine"})

    def signatures(self) -> dict[str, str]:
        """doc_id -> signature of the file version that is indexed."""
        return {m["doc_id"]: m.get("sig", "") for m in self._col.get(include=["metadatas"])["metadatas"]}

    def replace_all(self, items: list[tuple[DocMeta, list[str]]]) -> None:
        self.update(items, set())

    def update(self, items: list[tuple[DocMeta, list[str]]], keep: set[str]) -> None:
        """Index `items` (new or changed docs); drop every indexed doc that is neither in `items` nor in `keep`."""
        # embed everything first so a failure (Ollama down) leaves the old index intact
        # file name is embedded with the chunk so name-style queries match; it is never shown to staff
        embedded = [
            (meta, chunks, self._embed([f"{meta.rel_path}\n{c}" for c in chunks]))
            for meta, chunks in items if chunks
        ]
        shared = [m for m, _, _ in embedded if m.downloadable]
        name_docs = [f"{Path(m.rel_path).stem}\n{m.summary}".strip() for m in shared]  # not the folder: files of one topic share it, which blurs them together
        name_vecs = self._embed(name_docs) if shared else []
        col, names = self._col, self._names
        drop = (set(self.signatures()) - keep) | {m.doc_id for m, _, _ in embedded}
        if drop:
            col.delete(where={"doc_id": {"$in": sorted(drop)}})
            names.delete(ids=sorted(drop))
        if shared:
            names.add(
                ids=[m.doc_id for m in shared], embeddings=name_vecs,
                documents=name_docs,
                metadatas=[{"rel_path": m.rel_path, "category": m.category} for m in shared],
            )
        for meta, chunks, vectors in embedded:
            col.add(
                ids=[f"{meta.doc_id}:{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=vectors,
                metadatas=[
                    {"doc_id": meta.doc_id, "category": meta.category, "downloadable": meta.downloadable,
                     "mtime": meta.mtime, "rel_path": meta.rel_path, "sig": meta.sig}
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
            Hit(text=doc, distance=dist, **{k: v for k, v in meta.items() if k != "sig"})
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def find_files(self, question: str, k: int, category: str | None = None) -> list[NameHit]:
        """Downloadable files whose name and summary are closest to the question, best first; optionally only one topic folder."""
        where = {"category": category} if category else None
        n = len(self._names.get(where=where)["ids"])
        if n == 0:
            return []
        res = self._names.query(query_embeddings=self._embed([question]), n_results=min(k, n), where=where)
        return [
            NameHit(i, m["rel_path"], d, m["category"], doc.partition("\n")[2].strip())  # the document is "name\nsummary"
            for i, m, d, doc in zip(res["ids"][0], res["metadatas"][0], res["distances"][0], res["documents"][0])
        ]

    def summaries(self, ids: list[str] | None = None) -> dict[str, str]:
        """doc_id -> Thai summary of downloadable files (all of them, or only `ids`). First paragraph only: the keyword list after it is for search, not for display."""
        if ids == []:
            return {}
        res = self._names.get(ids=ids)
        return {i: display_summary(d.partition("\n")[2].strip()) for i, d in zip(res["ids"], res["documents"])}

    def topics(self) -> dict[str, int]:
        """Topic folder -> number of downloadable files in it."""
        out: dict[str, int] = {}
        for m in self._names.get(include=["metadatas"])["metadatas"]:
            out[m["category"]] = out.get(m["category"], 0) + 1
        return out

    def categories(self) -> list[str]:
        return sorted({m["category"] for m in self._col.get(include=["metadatas"])["metadatas"]})

    def doc_path(self, doc_id: str) -> str | None:
        res = self._col.get(where={"doc_id": doc_id}, limit=1)
        return res["metadatas"][0]["rel_path"] if res["metadatas"] else None
