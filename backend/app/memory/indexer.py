from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock, Thread

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.llm.embedding_client import bailian_embedding_client
from app.storage.db import SessionLocal
from app.storage.models import KnowledgeChunk


class MemoryIndexer:
    """Async single-worker embedding indexer.

    Writes are intentionally decoupled from script generation: saving a version creates
    text chunks immediately, then this background worker fills embeddings later.
    """

    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._lock = Lock()
        self._started = False
        self._stats = {
            "queued": 0,
            "indexed": 0,
            "failed": 0,
            "last_error": "",
            "last_indexed_at": "",
        }

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        thread = Thread(target=self._run, name="memory-indexer", daemon=True)
        thread.start()

    def enqueue(self, chunk_ids: list[str]) -> None:
        if not settings.enable_vector_memory:
            return
        self.start()
        for chunk_id in chunk_ids:
            self._queue.put(chunk_id)
        with self._lock:
            self._stats["queued"] += len(chunk_ids)

    def enqueue_pending(self, limit: int = 100) -> int:
        if not settings.enable_vector_memory:
            return 0
        try:
            with SessionLocal() as session:
                chunks = (
                    session.query(KnowledgeChunk.id)
                    .filter(KnowledgeChunk.embedding_status.in_(("pending", "failed")))
                    .order_by(KnowledgeChunk.created_at.asc())
                    .limit(limit)
                    .all()
                )
        except SQLAlchemyError:
            return 0
        chunk_ids = [str(row[0]) for row in chunks]
        self.enqueue(chunk_ids)
        return len(chunk_ids)

    def status(self) -> dict:
        with self._lock:
            stats = dict(self._stats)
        stats["chunk_counts"] = self._chunk_counts()
        embedding_status = bailian_embedding_client.status()
        stats.update(
            {
                "running": self._started,
                "queue_size": self._queue.qsize(),
                "provider": embedding_status["provider"],
                "model": embedding_status["model"],
                "configured_device": embedding_status["configured_device"],
                "runtime_device": embedding_status["runtime_device"],
            }
        )
        return stats

    def _chunk_counts(self) -> dict[str, int]:
        if not settings.enable_vector_memory:
            return {}
        try:
            with SessionLocal() as session:
                rows = (
                    session.query(KnowledgeChunk.embedding_status, func.count(KnowledgeChunk.id))
                    .group_by(KnowledgeChunk.embedding_status)
                    .all()
                )
        except SQLAlchemyError:
            return {}
        return {str(status or "unknown"): int(count) for status, count in rows}

    def _run(self) -> None:
        while True:
            try:
                chunk_id = self._queue.get(timeout=2)
            except Empty:
                continue
            self._index_chunk(chunk_id)
            self._queue.task_done()

    def _index_chunk(self, chunk_id: str) -> None:
        try:
            with SessionLocal() as session:
                chunk = session.get(KnowledgeChunk, chunk_id)
                if not chunk:
                    return
                chunk.embedding_status = "indexing"
                chunk.embedding_error = ""
                session.commit()

                embedding = bailian_embedding_client.embed_text(chunk.text)
                chunk = session.get(KnowledgeChunk, chunk_id)
                if not chunk:
                    return
                chunk.embedding = embedding
                chunk.embedding_status = "indexed" if embedding else "failed"
                chunk.embedding_error = "" if embedding else "Embedding provider returned no vector."
                chunk.indexed_at = datetime.now(timezone.utc) if embedding else None
                session.commit()
                self._record_success() if embedding else self._record_failure(chunk.embedding_error)
        except Exception as exc:
            self._record_failure(str(exc))
            self._mark_failed(chunk_id, str(exc))

    def _mark_failed(self, chunk_id: str, error: str) -> None:
        try:
            with SessionLocal() as session:
                chunk = session.get(KnowledgeChunk, chunk_id)
                if not chunk:
                    return
                chunk.embedding_status = "failed"
                chunk.embedding_error = error[:1000]
                session.commit()
        except SQLAlchemyError:
            pass

    def _record_success(self) -> None:
        with self._lock:
            self._stats["indexed"] += 1
            self._stats["last_indexed_at"] = datetime.now(timezone.utc).isoformat()

    def _record_failure(self, error: str) -> None:
        with self._lock:
            self._stats["failed"] += 1
            self._stats["last_error"] = error[:1000]


memory_indexer = MemoryIndexer()
