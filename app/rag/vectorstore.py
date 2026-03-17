"""
ChromaDB-backed RAG vector store for regulatory and standards documents.

ChromaDB's built-in default embedding model (all-MiniLM-L6-v2) handles
vectorisation automatically — no external embedding API call is required.

Seed documents (HIPAA, GDPR, PCI-DSS, WCAG, IEEE 830, SRS template guidance) are loaded from the
``seed_data/`` directory on startup if the collection is empty.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

logger = logging.getLogger(__name__)

_SEED_DATA_DIR = Path(__file__).parent / "seed_data"

# Module-level singletons initialised by `init_vectorstore()`
_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def init_vectorstore() -> None:
    """
    Initialise the ChromaDB persistent client and sync the seed documents
    into the regulatory documents collection.

    Call once during FastAPI lifespan startup.
    """
    global _client, _collection

    settings = get_settings()
    _client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    _collection = _client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )

    existing_count = _collection.count()
    _seed_collection(
        _collection,
        existing_count=existing_count,
        seed_if_empty=settings.vectorstore_seed_if_empty,
        force_reseed=settings.vectorstore_force_reseed,
    )
    logger.info(
        "ChromaDB collection '%s' synced from seed data (%d -> %d chunks).",
        settings.chroma_collection,
        existing_count,
        _collection.count(),
    )


def _seed_collection(
    collection: chromadb.Collection,
    *,
    existing_count: int,
    seed_if_empty: bool,
    force_reseed: bool,
) -> None:
    """Load all .txt files from seed_data/ into the collection."""
    if seed_if_empty and existing_count > 0 and not force_reseed:
        logger.info(
            "Skipping seed sync because collection already has %d chunks.",
            existing_count,
        )
        return

    seed_files = sorted(_SEED_DATA_DIR.glob("*.txt"))
    if not seed_files:
        logger.warning("No seed data files found in %s", _SEED_DATA_DIR)
        return

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for txt_file in seed_files:
        text = txt_file.read_text(encoding="utf-8")
        # Split into paragraphs (double-newline separated) for granular retrieval
        chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{txt_file.stem}-{idx}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({"source": txt_file.name, "chunk": idx})

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(
        "Seeded ChromaDB collection with %d chunks from %d files.",
        len(ids),
        len(seed_files),
    )


def retrieve(query: str, n_results: int = 5) -> str:
    """
    Perform a semantic similarity search and return concatenated document chunks.

    Args:
        query:     Natural-language query string.
        n_results: Number of top-matching chunks to return.

    Returns:
        A single string of newline-joined retrieved chunks, or an empty string
        if the vector store has not been initialised.
    """
    if _collection is None:
        logger.error("Vector store not initialised — call init_vectorstore() first.")
        return ""

    results = _collection.query(
        query_texts=[query],
        n_results=min(n_results, _collection.count()),
        include=["documents", "metadatas"],
    )

    chunks: list[str] = []
    docs_list = results.get("documents", [[]])
    meta_list = results.get("metadatas", [[]])

    for doc, meta in zip(docs_list[0], meta_list[0]):
        source = meta.get("source", "unknown") if meta else "unknown"
        chunks.append(f"[{source}]\n{doc}")

    return "\n\n---\n\n".join(chunks)
