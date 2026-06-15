"""
backend/core/vector_store.py
─────────────────────────────
ChromaDB integration for per-repository code knowledge storage.

Features:
- Lazy client initialisation with retry
- Per-repository collection management (create / get / delete)
- Embedding via nomic-embed-text (via Ollama) or sentence-transformers fallback
- add_documents(), search(), delete(), get_collection_stats()
- Metadata filtering support
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

import chromadb
from chromadb import Collection
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import (
    EmbeddingFunction,
    SentenceTransformerEmbeddingFunction,
)

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Embedding function ────────────────────────────────────────────────────────

class OllamaEmbeddingFunction(EmbeddingFunction):
    """Embedding function that calls Ollama's nomic-embed-text model.

    Falls back to sentence-transformers if Ollama is unavailable.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._fallback: Optional[SentenceTransformerEmbeddingFunction] = None

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        import httpx

        try:
            embeddings: list[list[float]] = []
            with httpx.Client(timeout=30) as client:
                for text in input:
                    resp = client.post(
                        f"{self._base_url}/api/embeddings",
                        json={"model": self._model, "prompt": text},
                    )
                    resp.raise_for_status()
                    embeddings.append(resp.json()["embedding"])
            return embeddings

        except Exception as exc:
            logger.warning(
                "Ollama embedding failed (%s), falling back to sentence-transformers",
                exc,
            )
            return self._get_fallback()(input)

    def _get_fallback(self) -> SentenceTransformerEmbeddingFunction:
        if self._fallback is None:
            self._fallback = SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        return self._fallback


# ── Client singleton ──────────────────────────────────────────────────────────

_client: Optional[chromadb.HttpClient] = None
_embedding_fn: Optional[EmbeddingFunction] = None


def _get_embedding_fn() -> EmbeddingFunction:
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = OllamaEmbeddingFunction(
            model="nomic-embed-text",
            base_url=settings.OLLAMA_BASE_URL,
        )
    return _embedding_fn


def get_chroma_client() -> chromadb.HttpClient:
    """Return the singleton ChromaDB HTTP client.

    Raises:
        RuntimeError: if ChromaDB is unreachable after multiple attempts.
    """
    global _client
    if _client is not None:
        return _client

    import time

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST,
                port=settings.CHROMADB_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=settings.is_development,
                ),
            )
            # Verify connectivity
            client.heartbeat()
            _client = client
            logger.info(
                "ChromaDB connected at %s:%d", settings.CHROMADB_HOST, settings.CHROMADB_PORT
            )
            return _client
        except Exception as exc:
            logger.warning(
                "ChromaDB connection attempt %d/%d failed: %s", attempt, max_attempts, exc
            )
            if attempt < max_attempts:
                time.sleep(2 ** attempt)

    # Last resort: in-memory client for development
    logger.error(
        "ChromaDB unreachable after %d attempts; using ephemeral in-process client",
        max_attempts,
    )
    _client = chromadb.Client()
    return _client


# ── Collection name helpers ────────────────────────────────────────────────────

def _sanitise_collection_name(name: str) -> str:
    """ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens."""
    import re
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
    name = name[:63]
    # Must not start/end with hyphen
    name = name.strip("-")
    if len(name) < 3:
        name = f"col-{name}"
    return name.lower()


def collection_name_for_repo(repository_id: str, suffix: str = "code") -> str:
    """Generate a deterministic ChromaDB collection name for a repository."""
    short_id = repository_id.replace("-", "")[:12]
    return _sanitise_collection_name(f"repo-{short_id}-{suffix}")


# ── Collection management ─────────────────────────────────────────────────────

def get_or_create_collection(name: str, metadata: Optional[dict] = None) -> Collection:
    """Get an existing collection or create a new one.

    Args:
        name:     Collection identifier (will be sanitised).
        metadata: Optional collection-level metadata.

    Returns:
        ChromaDB Collection object.
    """
    client = get_chroma_client()
    safe_name = _sanitise_collection_name(name)
    collection = client.get_or_create_collection(
        name=safe_name,
        embedding_function=_get_embedding_fn(),
        metadata=metadata or {"hnsw:space": "cosine"},
    )
    logger.debug("Collection '%s' ready (documents: %d)", safe_name, collection.count())
    return collection


def delete_collection(name: str) -> bool:
    """Delete a collection by name.

    Returns:
        True if deleted, False if not found.
    """
    client = get_chroma_client()
    safe_name = _sanitise_collection_name(name)
    try:
        client.delete_collection(safe_name)
        logger.info("Collection '%s' deleted", safe_name)
        return True
    except Exception as exc:
        logger.warning("Could not delete collection '%s': %s", safe_name, exc)
        return False


def list_collections() -> list[str]:
    """Return the names of all existing collections."""
    client = get_chroma_client()
    return [c.name for c in client.list_collections()]


def get_collection_stats(name: str) -> dict:
    """Return document count and metadata for a collection."""
    client = get_chroma_client()
    safe_name = _sanitise_collection_name(name)
    try:
        col = client.get_collection(
            name=safe_name, embedding_function=_get_embedding_fn()
        )
        return {
            "name": safe_name,
            "count": col.count(),
            "metadata": col.metadata,
        }
    except Exception as exc:
        return {"name": safe_name, "count": 0, "error": str(exc)}


# ── Document operations ───────────────────────────────────────────────────────

def _make_chunk_id(text: str, file_path: str, start_line: int) -> str:
    """Generate a stable deterministic ID for a code chunk."""
    raw = f"{file_path}:{start_line}:{text[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def add_documents(
    collection_name: str,
    documents: list[str],
    metadatas: Optional[list[dict]] = None,
    ids: Optional[list[str]] = None,
    batch_size: int = 100,
) -> int:
    """Add or upsert documents into a collection.

    Args:
        collection_name: Target collection identifier.
        documents:       List of text chunks to embed and store.
        metadatas:       Parallel list of metadata dicts (optional).
        ids:             Parallel list of document IDs (auto-generated if None).
        batch_size:      Maximum number of documents per ChromaDB upsert call.

    Returns:
        Number of documents upserted.
    """
    if not documents:
        return 0

    collection = get_or_create_collection(collection_name)

    # Auto-generate IDs from content hash if not provided
    if ids is None:
        ids = [
            _make_chunk_id(doc, (metadatas[i] or {}).get("file_path", ""), i)
            if metadatas
            else hashlib.md5(doc.encode()).hexdigest()
            for i, doc in enumerate(documents)
        ]

    effective_metadatas = metadatas or [{} for _ in documents]
    total = 0

    # Batch upsert to avoid memory issues with large repos
    for start in range(0, len(documents), batch_size):
        batch_docs = documents[start : start + batch_size]
        batch_ids = ids[start : start + batch_size]
        batch_meta = effective_metadatas[start : start + batch_size]

        # ChromaDB rejects None values in metadata
        cleaned_meta = [
            {k: v for k, v in m.items() if v is not None} for m in batch_meta
        ]

        collection.upsert(
            documents=batch_docs,
            ids=batch_ids,
            metadatas=cleaned_meta,
        )
        total += len(batch_docs)
        logger.debug(
            "Upserted %d/%d documents to '%s'", total, len(documents), collection_name
        )

    return total


def search(
    collection_name: str,
    query: str,
    n_results: int = 10,
    where: Optional[dict] = None,
    where_document: Optional[dict] = None,
    include: Optional[list[str]] = None,
) -> list[dict]:
    """Semantic search within a collection.

    Args:
        collection_name:  Target collection identifier.
        query:            Natural-language or code query string.
        n_results:        Maximum number of results to return.
        where:            ChromaDB metadata filter (e.g. ``{"chunk_type": "function"}``).
        where_document:   ChromaDB document filter.
        include:          Fields to include in response (default: documents, metadatas, distances).

    Returns:
        List of dicts with keys: id, document, metadata, distance.
    """
    collection = get_or_create_collection(collection_name)

    if collection.count() == 0:
        return []

    effective_include = include or ["documents", "metadatas", "distances"]
    kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": min(n_results, collection.count()),
        "include": effective_include,
    }
    if where:
        kwargs["where"] = where
    if where_document:
        kwargs["where_document"] = where_document

    results = collection.query(**kwargs)

    output: list[dict] = []
    for i, doc_id in enumerate(results["ids"][0]):
        entry: dict = {"id": doc_id}
        if "documents" in effective_include:
            entry["document"] = results["documents"][0][i]
        if "metadatas" in effective_include:
            entry["metadata"] = results["metadatas"][0][i]
        if "distances" in effective_include:
            entry["distance"] = results["distances"][0][i]
        output.append(entry)

    return output


def delete_documents(collection_name: str, ids: list[str]) -> int:
    """Delete specific documents by ID from a collection.

    Returns:
        Number of IDs submitted for deletion.
    """
    if not ids:
        return 0
    collection = get_or_create_collection(collection_name)
    collection.delete(ids=ids)
    logger.info("Deleted %d documents from '%s'", len(ids), collection_name)
    return len(ids)


def get_documents_by_metadata(
    collection_name: str,
    where: dict,
    limit: int = 50,
) -> list[dict]:
    """Fetch documents matching a metadata filter without a query.

    Useful for retrieving all chunks of a specific file or type.
    """
    collection = get_or_create_collection(collection_name)
    if collection.count() == 0:
        return []

    results = collection.get(
        where=where,
        limit=limit,
        include=["documents", "metadatas"],
    )

    output: list[dict] = []
    for i, doc_id in enumerate(results["ids"]):
        output.append(
            {
                "id": doc_id,
                "document": results["documents"][i],
                "metadata": results["metadatas"][i],
            }
        )
    return output


# ── Repository-scoped helpers ─────────────────────────────────────────────────

class RepositoryVectorStore:
    """High-level interface scoped to a single repository's collections."""

    def __init__(self, repository_id: str) -> None:
        self.repository_id = repository_id
        self.code_collection = collection_name_for_repo(repository_id, "code")
        self.docs_collection = collection_name_for_repo(repository_id, "docs")

    def add_code_chunks(
        self,
        chunks: list[dict],
    ) -> int:
        """Add code chunks to the repository's code collection.

        Each chunk dict should have keys:
            text, file_path, chunk_type, start_line, end_line
        """
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "file_path": c.get("file_path", ""),
                "chunk_type": c.get("chunk_type", "unknown"),
                "start_line": c.get("start_line", 0),
                "end_line": c.get("end_line", 0),
                "repository_id": self.repository_id,
                "language": c.get("language", ""),
                "name": c.get("name", ""),
            }
            for c in chunks
        ]
        ids = [
            _make_chunk_id(c["text"], c.get("file_path", ""), c.get("start_line", 0))
            for c in chunks
        ]
        return add_documents(self.code_collection, documents, metadatas, ids)

    def search_code(
        self,
        query: str,
        n_results: int = 10,
        chunk_type: Optional[str] = None,
        file_path_prefix: Optional[str] = None,
    ) -> list[dict]:
        """Search code chunks with optional type/path filters."""
        where: dict = {"repository_id": self.repository_id}
        if chunk_type:
            where["chunk_type"] = chunk_type
        return search(self.code_collection, query, n_results=n_results, where=where)

    def add_docs(self, docs: list[dict]) -> int:
        """Add documentation chunks (README, wiki, etc.)."""
        documents = [d["text"] for d in docs]
        metadatas = [
            {
                "source": d.get("source", ""),
                "doc_type": d.get("doc_type", "readme"),
                "repository_id": self.repository_id,
            }
            for d in docs
        ]
        return add_documents(self.docs_collection, documents, metadatas)

    def search_docs(self, query: str, n_results: int = 5) -> list[dict]:
        """Search documentation chunks."""
        return search(self.docs_collection, query, n_results=n_results)

    def delete_all(self) -> None:
        """Remove both code and docs collections for this repository."""
        delete_collection(self.code_collection)
        delete_collection(self.docs_collection)

    def stats(self) -> dict:
        """Return document counts for both collections."""
        return {
            "code": get_collection_stats(self.code_collection),
            "docs": get_collection_stats(self.docs_collection),
        }
