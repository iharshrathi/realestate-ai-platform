"""Retrieval over verified property listings (the "R" in RAG).

The index is built from the ``properties`` table only, so anything retrieved is a real listing.
Two interchangeable backends:

* ``tfidf`` (default): scikit-learn TF-IDF, lexical retrieval, no heavy dependencies.
* ``sentence-transformers``: semantic embeddings stored in a FAISS index (optional extra,
  see ``requirements-embeddings.txt``). Falls back to TF-IDF if the packages are missing.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Property
from app.models.enums import PropertyStatus

logger = logging.getLogger(__name__)


def property_document(prop: Property) -> str:
    """The text that represents a listing in the index."""
    parts = [
        prop.title,
        f"{prop.property_type.value} in {prop.location}",
        f"{prop.bedrooms} BHK" if prop.bedrooms else "",
        f"priced at {prop.price_inr / 1e5:.0f} lakh",
        f"amenities: {', '.join(prop.amenities)}" if prop.amenities else "",
        prop.description,
    ]
    return ". ".join(p for p in parts if p)


class Backend(Protocol):
    def build(self, documents: list[str]) -> None: ...
    def search(self, query: str, k: int) -> list[tuple[int, float]]: ...


class TfidfBackend:
    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
        )
        self._matrix = None

    def build(self, documents: list[str]) -> None:
        self._matrix = self._vectorizer.fit_transform(documents) if documents else None

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        if self._matrix is None or not query.strip():
            return []
        scores = (self._matrix @ self._vectorizer.transform([query]).T).toarray().ravel()
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]


class FaissBackend:
    def __init__(self, model_name: str) -> None:
        import faiss  # type: ignore[import-not-found]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self._faiss = faiss
        self._encoder = SentenceTransformer(model_name)
        self._index = None

    def build(self, documents: list[str]) -> None:
        if not documents:
            self._index = None
            return
        vectors = self._encoder.encode(documents, normalize_embeddings=True).astype("float32")
        self._index = self._faiss.IndexFlatIP(vectors.shape[1])
        self._index.add(vectors)

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        if self._index is None or not query.strip():
            return []
        vector = self._encoder.encode([query], normalize_embeddings=True).astype("float32")
        scores, ids = self._index.search(vector, min(k, self._index.ntotal))
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0], strict=True) if i >= 0]


def _make_backend() -> Backend:
    settings = get_settings()
    if settings.embedding_backend == "sentence-transformers":
        try:
            return FaissBackend(settings.embedding_model)
        except ImportError:
            logger.warning(
                "sentence-transformers/faiss not installed; falling back to TF-IDF retrieval"
            )
    return TfidfBackend()


@dataclass(frozen=True)
class Hit:
    property: Property
    score: float


class PropertyIndex:
    """In-memory index over available listings; rebuilt automatically when listings change."""

    def __init__(self) -> None:
        self._backend: Backend | None = None
        self._ids: list[int] = []
        self._signature: tuple | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _signature_of(db: Session) -> tuple:
        row = db.execute(
            select(
                func.count(Property.id),
                func.coalesce(func.sum(Property.id), 0),
                func.max(Property.updated_at),
            ).where(Property.status == PropertyStatus.AVAILABLE)
        ).one()
        return tuple(row)

    def ensure_fresh(self, db: Session) -> None:
        signature = self._signature_of(db)
        with self._lock:
            if self._backend is not None and signature == self._signature:
                return
            properties = list(
                db.scalars(
                    select(Property)
                    .where(Property.status == PropertyStatus.AVAILABLE)
                    .order_by(Property.id)
                )
            )
            self._backend = _make_backend()
            self._backend.build([property_document(p) for p in properties])
            self._ids = [p.id for p in properties]
            self._signature = signature
            logger.info("Rebuilt property index with %d listings", len(properties))

    def search(self, db: Session, query: str, k: int = 5) -> list[Hit]:
        self.ensure_fresh(db)
        assert self._backend is not None
        hits = self._backend.search(query, k)
        if not hits:
            return []
        by_id = {
            p.id: p
            for p in db.scalars(
                select(Property).where(Property.id.in_([self._ids[i] for i, _ in hits]))
            )
        }
        return [Hit(by_id[self._ids[i]], score) for i, score in hits if self._ids[i] in by_id]

    def reset(self) -> None:
        with self._lock:
            self._backend, self._signature = None, None


property_index = PropertyIndex()
