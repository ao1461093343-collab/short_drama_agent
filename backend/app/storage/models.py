from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.storage.db import Base


class ScriptProject(Base):
    __tablename__ = "script_projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(50), default="Douyin")
    genre: Mapped[str] = mapped_column(String(80))
    brief: Mapped[str] = mapped_column(Text, default="")
    bible: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("script_projects.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200), default="")
    episode: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("script_projects.id", ondelete="CASCADE"))
    version_id: Mapped[str | None] = mapped_column(ForeignKey("script_versions.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(120))
    chunk_type: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dimension))
    embedding_status: Mapped[str] = mapped_column(String(20), default="pending")
    embedding_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
