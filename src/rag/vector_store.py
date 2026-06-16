"""Vector store with Qdrant (preferred) → Pinecone → in-memory fallback."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from rich.console import Console

from src.config import settings
from src.rag.chunker import ReviewChunk
from src.rag.embedder import Embedder, EMBEDDING_DIM

console = Console()


class VectorStore:
    """Unified vector store: tries Qdrant, then Pinecone, then in-memory."""

    def __init__(self):
        self.embedder = Embedder()
        self._backend: str = "memory"
        self._qdrant = None
        self._pinecone_index = None
        self._memory: list[dict] = []
        self._collection = settings.qdrant_collection

        self._init_qdrant() or self._init_pinecone()

    def _init_qdrant(self) -> bool:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            kwargs: dict = {"url": settings.qdrant_url}
            if settings.qdrant_api_key:
                kwargs["api_key"] = settings.qdrant_api_key

            client = QdrantClient(**kwargs, timeout=5)
            collections = [c.name for c in client.get_collections().collections]

            if self._collection not in collections:
                client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                console.print(f"[cyan]Created Qdrant collection '{self._collection}'")

            self._qdrant = client
            self._backend = "qdrant"
            console.print(f"[green]Connected to Qdrant at {settings.qdrant_url}")
            return True
        except Exception as e:
            console.print(f"[yellow]Qdrant unavailable ({type(e).__name__}), trying Pinecone...")
            return False

    def _init_pinecone(self) -> bool:
        if not settings.pinecone_api_key:
            console.print("[yellow]No Pinecone key — using in-memory vector store")
            return False
        try:
            from pinecone import Pinecone, ServerlessSpec

            pc = Pinecone(api_key=settings.pinecone_api_key)
            idx_name = settings.pinecone_index_name
            existing = [i.name for i in pc.list_indexes()]

            if idx_name not in existing:
                pc.create_index(
                    name=idx_name,
                    dimension=EMBEDDING_DIM,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region=settings.pinecone_environment),
                )
                time.sleep(5)

            self._pinecone_index = pc.Index(idx_name)
            self._backend = "pinecone"
            console.print(f"[green]Connected to Pinecone index '{idx_name}'")
            return True
        except Exception as e:
            console.print(f"[yellow]Pinecone unavailable ({e}), using in-memory store")
            return False

    # ── upsert ──────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[ReviewChunk], batch_size: int = 100) -> None:
        if not chunks:
            return
        pairs = self.embedder.embed_chunks(chunks)

        if self._backend == "qdrant":
            self._upsert_qdrant(pairs, batch_size)
        elif self._backend == "pinecone":
            self._upsert_pinecone(pairs, batch_size)
        else:
            for chunk, emb in pairs:
                self._memory.append({
                    "id": chunk.chunk_id,
                    "values": emb,
                    "metadata": chunk.metadata,
                    "text": chunk.text,
                })
            console.print(f"[yellow]Stored {len(pairs)} vectors in memory")

    def _upsert_qdrant(self, pairs: list[tuple[ReviewChunk, list[float]]], batch_size: int) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=abs(hash(c.chunk_id)) % (2**63),
                vector=emb,
                payload={**c.metadata, "chunk_id": c.chunk_id, "text": c.text},
            )
            for c, emb in pairs
        ]
        for i in range(0, len(points), batch_size):
            self._qdrant.upsert(
                collection_name=self._collection,
                points=points[i : i + batch_size],
            )
            console.print(f"[cyan]Qdrant upserted {min(i + batch_size, len(points))}/{len(points)}")

    def _upsert_pinecone(self, pairs: list[tuple[ReviewChunk, list[float]]], batch_size: int) -> None:
        vectors = [
            {"id": c.chunk_id, "values": emb, "metadata": c.metadata}
            for c, emb in pairs
        ]
        for i in range(0, len(vectors), batch_size):
            self._pinecone_index.upsert(vectors=vectors[i : i + batch_size])
            console.print(f"[cyan]Pinecone upserted {min(i + batch_size, len(vectors))}/{len(vectors)}")

    # ── query ────────────────────────────────────────────────────────────────

    def query(self, query: str, top_k: int = 10, filter: Optional[dict] = None) -> list[dict]:
        emb = self.embedder.embed_query(query)

        if self._backend == "qdrant":
            return self._query_qdrant(emb, top_k, filter)
        elif self._backend == "pinecone":
            return self._query_pinecone(emb, top_k, filter)
        else:
            return self._query_memory(emb, top_k, filter)

    def _query_qdrant(self, emb: list[float], top_k: int, filter: Optional[dict]) -> list[dict]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_filter = None
        if filter:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = self._qdrant.search(
            collection_name=self._collection,
            query_vector=emb,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [{"id": r.payload.get("chunk_id", str(r.id)), "score": r.score, "metadata": r.payload} for r in results]

    def _query_pinecone(self, emb: list[float], top_k: int, filter: Optional[dict]) -> list[dict]:
        kwargs = {"vector": emb, "top_k": top_k, "include_metadata": True}
        if filter:
            kwargs["filter"] = filter
        result = self._pinecone_index.query(**kwargs)
        return [{"id": m.id, "score": m.score, "metadata": m.metadata} for m in result.matches]

    def _query_memory(self, emb: list[float], top_k: int, filter: Optional[dict]) -> list[dict]:
        q = np.array(emb)
        results = []
        for item in self._memory:
            if filter and not all(item.get("metadata", {}).get(k) == v for k, v in filter.items()):
                continue
            v = np.array(item["values"])
            nq, nv = np.linalg.norm(q), np.linalg.norm(v)
            score = float(np.dot(q, v) / (nq * nv)) if nq > 0 and nv > 0 else 0.0
            results.append({"id": item["id"], "score": score, "metadata": item.get("metadata", {})})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
