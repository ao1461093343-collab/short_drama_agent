from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.sql import text

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    statements = [
        statement.strip()
        for statement in schema_path.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        _ensure_embedding_dimension(connection)


def _ensure_embedding_dimension(connection) -> None:
    expected_type = f"vector({settings.embedding_dimension})"
    current_type = connection.execute(
        text(
            """
            SELECT format_type(attribute.atttypid, attribute.atttypmod)
            FROM pg_attribute AS attribute
            WHERE attribute.attrelid = 'knowledge_chunks'::regclass
              AND attribute.attname = 'embedding'
              AND NOT attribute.attisdropped
            """
        )
    ).scalar()

    if current_type in {None, expected_type}:
        return

    connection.execute(text("DROP INDEX IF EXISTS knowledge_chunks_embedding_idx"))
    connection.execute(
        text(
            f"ALTER TABLE knowledge_chunks "
            f"ALTER COLUMN embedding TYPE vector({settings.embedding_dimension}) USING NULL"
        )
    )
    connection.execute(
        text(
            """
            UPDATE knowledge_chunks
            SET embedding_status = 'pending',
                embedding_error = 'Embedding dimension changed; reindex required.',
                indexed_at = NULL
            WHERE embedding_status IN ('indexed', 'indexing', 'failed')
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
            ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )
    )


def database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
