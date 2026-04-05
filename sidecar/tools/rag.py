"""RAG (Retrieval-Augmented Generation) tools using ChromaDB.

Persistent client stored at ~/.narrative-ide/chroma_db.
Collections are named per-project: narrative_{project_id}_metadata.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def _get_client():
    """Return a persistent ChromaDB client."""
    import chromadb  # type: ignore[import]
    chroma_path = Path.home() / ".narrative-ide" / "chroma_db"
    chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_path))


def embed_chunks(chunks: list[dict], collection_name: str, metadata: dict) -> None:
    """Embed a list of chunk dicts and store in the named ChromaDB collection.

    Each chunk dict must have at least a 'content' key.
    The metadata dict is merged into per-chunk metadata.
    """
    if not chunks:
        return

    client = _get_client()
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []

    for chunk in chunks:
        content = chunk.get("content", "")
        if not content.strip():
            continue
        # Stable ID from content hash + collection name
        chunk_hash = hashlib.sha256(f"{collection_name}:{content[:200]}".encode()).hexdigest()[:16]
        chunk_id = f"{collection_name}_{chunk_hash}"
        chunk_meta = {**metadata, "chunk_id": chunk.get("chunk_id", 0)}

        documents.append(content)
        ids.append(chunk_id)
        metadatas.append(chunk_meta)

    if documents:
        collection.upsert(documents=documents, ids=ids, metadatas=metadatas)


def rag_search(query: str, collection_name: str, n_results: int = 5) -> list[dict]:
    """Query the named ChromaDB collection and return matching chunks.

    Returns a list of dicts with keys: content, metadata, distance.
    Returns an empty list if the collection doesn't exist or has no documents.
    """
    if not query.strip():
        return []

    try:
        client = _get_client()
        collection = client.get_collection(name=collection_name)
        results = collection.query(query_texts=[query], n_results=n_results)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {"content": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(docs, metas, distances)
        ]
    except Exception:
        # Collection doesn't exist or other error — return empty
        return []
