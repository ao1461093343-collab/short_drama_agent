import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.graph.nodes.llm_helpers import ensure_list
from app.llm.embedding_client import bailian_embedding_client
from app.memory.indexer import memory_indexer
from app.storage.db import SessionLocal, database_available, initialize_database
from app.storage.models import KnowledgeChunk, ScriptProject, ScriptVersion


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DATA_DIR.mkdir(exist_ok=True)
PROJECTS_FILE = DATA_DIR / "projects.json"


class JsonProjectRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        if not PROJECTS_FILE.exists():
            PROJECTS_FILE.write_text("[]", encoding="utf-8")

    def list_projects(self) -> list[dict]:
        projects = self._read()
        return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)

    def get_project(self, project_id: str) -> dict | None:
        return next((project for project in self._read() if project["id"] == project_id), None)

    def create_project(self, title: str, platform: str, genre: str, brief: str) -> dict:
        now = self._now()
        project = {
            "id": str(uuid4()),
            "title": title or brief[:40] or "Untitled Short Drama Project",
            "platform": platform,
            "genre": genre,
            "brief": brief,
            "versions": [],
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            projects = self._read_unlocked()
            projects.append(project)
            self._write_unlocked(projects)
        return project

    def save_version(self, project_id: str | None, result: dict, title: str | None = None) -> dict:
        with self._lock:
            projects = self._read_unlocked()
            project = next((item for item in projects if item["id"] == project_id), None)
            if project is None:
                project = self._build_project(project_id, result, title)
                projects.append(project)

            version = self._build_version(project, result, title)
            project["versions"].insert(0, version)
            project["updated_at"] = version["created_at"]
            self._write_unlocked(projects)
            return {"project": project, "version": version}

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            projects = self._read_unlocked()
            next_projects = [project for project in projects if project.get("id") != project_id]
            if len(next_projects) == len(projects):
                return False
            self._write_unlocked(next_projects)
            return True

    def delete_version(self, project_id: str, version_id: str) -> bool:
        with self._lock:
            projects = self._read_unlocked()
            project = next((item for item in projects if item.get("id") == project_id), None)
            if not project:
                return False
            versions = project.get("versions", [])
            next_versions = [version for version in versions if version.get("id") != version_id]
            if len(next_versions) == len(versions):
                return False
            for index, version in enumerate(reversed(next_versions), start=1):
                version["version_no"] = index
            project["versions"] = next_versions
            project["updated_at"] = self._now()
            self._write_unlocked(projects)
            return True

    def previous_episodes(self, project_id: str | None) -> list[dict]:
        if not project_id:
            return []
        project = self.get_project(project_id)
        if not project:
            return []
        return [_episode_memory_from_version(version) for version in reversed(project.get("versions", []))]

    def next_episode_number(self, project_id: str | None) -> int:
        return _next_episode_number_from_memory(self.previous_episodes(project_id))

    def search_memory(self, project_id: str | None, query: str, limit: int | None = None) -> list[dict]:
        return []

    def storage_status(self) -> dict:
        return {
            "backend": "json",
            "vector_memory_enabled": False,
            "projects_file": str(PROJECTS_FILE),
        }

    def _build_project(self, project_id: str | None, result: dict, title: str | None) -> dict:
        script = result.get("final_script", {})
        bible = result.get("project_bible", {})
        now = self._now()
        return {
            "id": project_id or str(uuid4()),
            "title": title or script.get("title") or bible.get("logline") or "Untitled Short Drama Project",
            "platform": result.get("platform", "Douyin"),
            "genre": result.get("genre", ""),
            "brief": result.get("user_brief", ""),
            "versions": [],
            "created_at": now,
            "updated_at": now,
        }

    def _build_version(self, project: dict, result: dict, title: str | None) -> dict:
        version_no = len(project["versions"]) + 1
        return {
            "id": str(uuid4()),
            "version_no": version_no,
            "title": title or result.get("final_script", {}).get("title") or f"Version {version_no}",
            "episode": result.get("episode_number")
            or result.get("final_script", {}).get("episode")
            or version_no,
            "summary": _summarize_result(result),
            "result": result,
            "created_at": self._now(),
        }

    def _read(self) -> list[dict]:
        with self._lock:
            return self._read_unlocked()

    @staticmethod
    def _read_unlocked() -> list[dict]:
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _write_unlocked(projects: list[dict]) -> None:
        PROJECTS_FILE.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


class PostgresProjectRepository:
    def __init__(self) -> None:
        initialize_database()
        self._import_json_projects_if_empty()

    def list_projects(self) -> list[dict]:
        with SessionLocal() as session:
            projects = (
                session.query(ScriptProject)
                .order_by(ScriptProject.updated_at.desc(), ScriptProject.created_at.desc())
                .all()
            )
            return [self._project_to_dict(session, project, include_versions=True) for project in projects]

    def get_project(self, project_id: str) -> dict | None:
        with SessionLocal() as session:
            project = session.get(ScriptProject, project_id)
            if not project:
                return None
            return self._project_to_dict(session, project, include_versions=True)

    def create_project(self, title: str, platform: str, genre: str, brief: str) -> dict:
        now = datetime.now(timezone.utc)
        project = ScriptProject(
            id=str(uuid4()),
            title=title or brief[:40] or "Untitled Short Drama Project",
            platform=platform,
            genre=genre,
            brief=brief,
            bible={},
            created_at=now,
            updated_at=now,
        )
        with SessionLocal() as session:
            session.add(project)
            session.commit()
            session.refresh(project)
            return self._project_to_dict(session, project, include_versions=True)

    def save_version(self, project_id: str | None, result: dict, title: str | None = None) -> dict:
        with SessionLocal() as session:
            project = session.get(ScriptProject, project_id) if project_id else None
            if project is None:
                project = self._create_project_from_result(project_id, result, title)
                session.add(project)
                session.flush()

            version_no = self._next_version_no(session, project.id)
            version = ScriptVersion(
                id=str(uuid4()),
                project_id=project.id,
                version_no=version_no,
                status=result.get("review_status") or "PASS",
                title=title or result.get("final_script", {}).get("title") or f"Version {version_no}",
                episode=result.get("episode_number")
                or result.get("final_script", {}).get("episode")
                or version_no,
                summary=_summarize_result(result),
                content=result,
                review_report={
                    "review_status": result.get("review_status"),
                    "review_findings": result.get("review_findings", []),
                    "trace": result.get("trace", []),
                },
            )
            project.title = title or project.title or version.title
            project.platform = result.get("platform") or project.platform
            project.genre = result.get("genre") or project.genre
            project.brief = result.get("user_brief") or project.brief
            project.bible = result.get("project_bible") or project.bible or {}
            project.updated_at = datetime.now(timezone.utc)

            session.add(version)
            session.flush()
            chunk_ids = self._store_memory_chunks(session, project.id, version.id, result, version.summary)
            session.commit()
            memory_indexer.enqueue(chunk_ids)
            session.refresh(project)
            session.refresh(version)
            return {
                "project": self._project_to_dict(session, project, include_versions=True),
                "version": self._version_to_dict(version),
            }

    def delete_project(self, project_id: str) -> bool:
        if not _is_uuid(project_id):
            return False
        with SessionLocal() as session:
            project = session.get(ScriptProject, project_id)
            if not project:
                return False
            session.query(KnowledgeChunk).filter(KnowledgeChunk.project_id == project_id).delete(
                synchronize_session=False
            )
            session.query(ScriptVersion).filter(ScriptVersion.project_id == project_id).delete(
                synchronize_session=False
            )
            session.delete(project)
            session.commit()
            return True

    def delete_version(self, project_id: str, version_id: str) -> bool:
        if not _is_uuid(project_id) or not _is_uuid(version_id):
            return False
        with SessionLocal() as session:
            version = (
                session.query(ScriptVersion)
                .filter(ScriptVersion.id == version_id, ScriptVersion.project_id == project_id)
                .first()
            )
            if not version:
                return False
            session.query(KnowledgeChunk).filter(KnowledgeChunk.version_id == version_id).delete(
                synchronize_session=False
            )
            session.delete(version)
            session.commit()
            return True

    def previous_episodes(self, project_id: str | None) -> list[dict]:
        if not project_id:
            return []
        with SessionLocal() as session:
            versions = (
                session.query(ScriptVersion)
                .filter(ScriptVersion.project_id == project_id)
                .order_by(ScriptVersion.version_no.asc(), ScriptVersion.created_at.asc())
                .all()
            )
            return [_episode_memory_from_version(self._version_to_dict(version)) for version in versions]

    def next_episode_number(self, project_id: str | None) -> int:
        return _next_episode_number_from_memory(self.previous_episodes(project_id))

    def search_memory(self, project_id: str | None, query: str, limit: int | None = None) -> list[dict]:
        if not project_id or not settings.enable_vector_memory:
            return []
        if not _is_uuid(project_id):
            return []
        embedding = _safe_embed_text(query)
        top_k = limit or settings.vector_memory_top_k

        try:
            with SessionLocal() as session:
                vector_results = self._vector_search(session, project_id, embedding, top_k * 2)
                keyword_results = self._keyword_search(session, project_id, query, top_k * 2)
                return _fuse_memory_results(vector_results, keyword_results, top_k)
        except SQLAlchemyError:
            return []

    def storage_status(self) -> dict:
        embedding_status = bailian_embedding_client.status()
        return {
            "backend": "postgres",
            "vector_memory_enabled": settings.enable_vector_memory,
            "embedding_provider": embedding_status["provider"],
            "embedding_model": embedding_status["model"],
            "embedding_configured_device": embedding_status["configured_device"],
            "embedding_runtime_device": embedding_status["runtime_device"],
            "embedding_dimension": settings.embedding_dimension,
            "vector_memory_top_k": settings.vector_memory_top_k,
            "retrieval": "hybrid_vector_keyword",
        }

    @staticmethod
    def _vector_search(
        session: Session,
        project_id: str,
        embedding: list[float] | None,
        limit: int,
    ) -> list[dict]:
        if not embedding:
            return []
        distance = KnowledgeChunk.embedding.cosine_distance(embedding).label("distance")
        rows = (
            session.query(KnowledgeChunk, distance)
            .filter(KnowledgeChunk.project_id == project_id)
            .filter(KnowledgeChunk.embedding.is_not(None))
            .filter(KnowledgeChunk.embedding_status == "indexed")
            .order_by(distance.asc())
            .limit(limit)
            .all()
        )
        return [
            _memory_result_from_chunk(
                chunk,
                score=round(1 - float(distance_value), 4),
                retrieval="vector",
            )
            for chunk, distance_value in rows
        ]

    @staticmethod
    def _keyword_search(session: Session, project_id: str, query: str, limit: int) -> list[dict]:
        tokens = _query_tokens(query)
        if not tokens:
            return []
        rows = (
            session.query(KnowledgeChunk)
            .filter(KnowledgeChunk.project_id == project_id)
            .order_by(KnowledgeChunk.created_at.desc())
            .limit(200)
            .all()
        )
        scored: list[dict] = []
        for chunk in rows:
            text = chunk.text or ""
            text_lower = text.lower()
            hits = sum(text_lower.count(token.lower()) for token in tokens)
            if hits <= 0:
                continue
            coverage = sum(1 for token in tokens if token.lower() in text_lower) / max(len(tokens), 1)
            score = hits + coverage
            scored.append(
                _memory_result_from_chunk(chunk, score=round(score, 4), retrieval="keyword")
            )
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    def _create_project_from_result(
        self,
        project_id: str | None,
        result: dict,
        title: str | None,
    ) -> ScriptProject:
        script = result.get("final_script", {})
        bible = result.get("project_bible", {})
        now = datetime.now(timezone.utc)
        return ScriptProject(
            id=project_id or str(uuid4()),
            title=title or script.get("title") or bible.get("logline") or "Untitled Short Drama Project",
            platform=result.get("platform", "Douyin"),
            genre=result.get("genre", ""),
            brief=result.get("user_brief", ""),
            bible=bible or {},
            created_at=now,
            updated_at=now,
        )

    def _project_to_dict(
        self,
        session: Session,
        project: ScriptProject,
        include_versions: bool,
    ) -> dict:
        versions = []
        if include_versions:
            versions = [
                self._version_to_dict(version)
                for version in (
                    session.query(ScriptVersion)
                    .filter(ScriptVersion.project_id == project.id)
                    .order_by(ScriptVersion.created_at.desc(), ScriptVersion.version_no.desc())
                    .all()
                )
            ]

        return {
            "id": str(project.id),
            "title": project.title,
            "platform": project.platform,
            "genre": project.genre,
            "brief": project.brief,
            "bible": project.bible or {},
            "versions": versions,
            "created_at": _iso(project.created_at),
            "updated_at": _iso(project.updated_at or project.created_at),
        }

    @staticmethod
    def _version_to_dict(version: ScriptVersion) -> dict:
        return {
            "id": str(version.id),
            "version_no": version.version_no,
            "title": version.title,
            "episode": version.episode,
            "summary": version.summary,
            "result": version.content or {},
            "review_report": version.review_report or {},
            "created_at": _iso(version.created_at),
        }

    @staticmethod
    def _next_version_no(session: Session, project_id: str) -> int:
        current = (
            session.query(func.max(ScriptVersion.version_no))
            .filter(ScriptVersion.project_id == project_id)
            .scalar()
        )
        return int(current or 0) + 1

    def _store_memory_chunks(
        self,
        session: Session,
        project_id: str,
        version_id: str,
        result: dict,
        summary: str,
    ) -> list[str]:
        chunk_ids: list[str] = []
        for chunk in _build_memory_chunks(result, summary):
            chunk_id = str(uuid4())
            chunk_ids.append(chunk_id)
            session.add(
                KnowledgeChunk(
                    id=chunk_id,
                    project_id=project_id,
                    version_id=version_id,
                    source=chunk["source"],
                    chunk_type=chunk["chunk_type"],
                    text=chunk["text"],
                    meta=chunk["meta"],
                    embedding=None,
                    embedding_status="pending",
                    embedding_error="",
                )
            )
        return chunk_ids

    def _import_json_projects_if_empty(self) -> None:
        if not PROJECTS_FILE.exists():
            return
        with SessionLocal() as session:
            if session.query(ScriptProject).limit(1).first():
                return
            try:
                projects = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return
            for project_data in projects:
                project = ScriptProject(
                    id=project_data.get("id") or str(uuid4()),
                    title=project_data.get("title") or "Untitled Short Drama Project",
                    platform=project_data.get("platform") or "Douyin",
                    genre=project_data.get("genre") or "",
                    brief=project_data.get("brief") or "",
                    bible={},
                    created_at=_parse_datetime(project_data.get("created_at")),
                    updated_at=_parse_datetime(project_data.get("updated_at")),
                )
                session.merge(project)
                session.flush()
                for version_data in reversed(project_data.get("versions", [])):
                    result = version_data.get("result", {})
                    version = ScriptVersion(
                        id=version_data.get("id") or str(uuid4()),
                        project_id=project.id,
                        version_no=version_data.get("version_no") or self._next_version_no(session, project.id),
                        status=result.get("review_status") or "PASS",
                        title=version_data.get("title") or result.get("final_script", {}).get("title") or "",
                        episode=version_data.get("episode") or result.get("episode_number"),
                        summary=version_data.get("summary") or _summarize_result(result),
                        content=result,
                        review_report={
                            "review_status": result.get("review_status"),
                            "review_findings": result.get("review_findings", []),
                            "trace": result.get("trace", []),
                        },
                        created_at=_parse_datetime(version_data.get("created_at")),
                    )
                    session.merge(version)
            session.commit()


class ProjectRepository:
    def __init__(self) -> None:
        self._json_repository = JsonProjectRepository()
        self._backend = self._select_backend()

    def list_projects(self) -> list[dict]:
        return self._backend.list_projects()

    def get_project(self, project_id: str) -> dict | None:
        return self._backend.get_project(project_id)

    def create_project(self, title: str, platform: str, genre: str, brief: str) -> dict:
        return self._backend.create_project(title, platform, genre, brief)

    def save_version(self, project_id: str | None, result: dict, title: str | None = None) -> dict:
        return self._backend.save_version(project_id, result, title)

    def delete_project(self, project_id: str) -> bool:
        return self._backend.delete_project(project_id)

    def delete_version(self, project_id: str, version_id: str) -> bool:
        return self._backend.delete_version(project_id, version_id)

    def previous_episodes(self, project_id: str | None) -> list[dict]:
        return self._backend.previous_episodes(project_id)

    def next_episode_number(self, project_id: str | None) -> int:
        return self._backend.next_episode_number(project_id)

    def search_memory(self, project_id: str | None, query: str, limit: int | None = None) -> list[dict]:
        return self._backend.search_memory(project_id, query, limit)

    def storage_status(self) -> dict:
        return self._backend.storage_status()

    def _select_backend(self):
        backend = settings.storage_backend.lower()
        if backend == "json":
            return self._json_repository
        if backend not in {"auto", "postgres"}:
            return self._json_repository

        try:
            if database_available():
                return PostgresProjectRepository()
        except SQLAlchemyError:
            if backend == "postgres":
                raise

        if backend == "postgres":
            return PostgresProjectRepository()
        return self._json_repository


def _build_memory_chunks(result: dict, summary: str) -> list[dict]:
    script = result.get("final_script", {}) or {}
    bible = result.get("project_bible", {}) or {}
    episode = result.get("episode_number") or script.get("episode")
    base_meta = {
        "episode": episode,
        "title": script.get("title"),
        "review_status": result.get("review_status"),
    }
    chunks: list[dict] = []

    if summary:
        chunks.append(
            {
                "source": "project_version",
                "chunk_type": "episode_summary",
                "text": _compact_text(
                    [
                        f"Episode {episode}: {script.get('title', '')}",
                        summary,
                        f"Ending hook: {script.get('ending_hook', '')}",
                    ]
                ),
                "meta": base_meta,
            }
        )

    ending_hook = script.get("ending_hook")
    if ending_hook:
        chunks.append(
            {
                "source": "final_script",
                "chunk_type": "open_thread",
                "text": str(ending_hook),
                "meta": {**base_meta, "field": "ending_hook"},
            }
        )

    for character in ensure_list(bible.get("characters"))[:12]:
        if not isinstance(character, dict):
            continue
        text = _compact_text(
            [
                character.get("name"),
                character.get("role"),
                character.get("profile"),
                character.get("desire"),
                character.get("current_state"),
            ]
        )
        if text:
            chunks.append(
                {
                    "source": "project_bible",
                    "chunk_type": "character_memory",
                    "text": text,
                    "meta": {**base_meta, "character": character.get("name")},
                }
            )

    for scene in ensure_list(script.get("scenes"))[:20]:
        if not isinstance(scene, dict):
            continue
        text = _compact_text(
            [
                f"Scene {scene.get('scene_no')}: {scene.get('location', '')}",
                scene.get("action"),
                " ".join(
                    _compact_text([line.get("speaker"), line.get("line")])
                    for line in ensure_list(scene.get("dialogue"))[:6]
                    if isinstance(line, dict)
                ),
            ]
        )
        if text:
            chunks.append(
                {
                    "source": "final_script",
                    "chunk_type": "scene_memory",
                    "text": text,
                    "meta": {**base_meta, "scene_no": scene.get("scene_no")},
                }
            )

    return chunks


def _next_episode_number_from_memory(previous_episodes: list[dict]) -> int:
    numbers = [
        int(item.get("episode"))
        for item in previous_episodes
        if isinstance(item, dict) and str(item.get("episode", "")).isdigit()
    ]
    return (max(numbers) + 1) if numbers else 1


def _episode_memory_from_version(version: dict) -> dict:
    result = version.get("result", {})
    script = result.get("final_script", {})
    return {
        "episode": script.get("episode") or version.get("episode"),
        "title": script.get("title") or version.get("title"),
        "summary": version.get("summary"),
        "ending_hook": script.get("ending_hook"),
        "status_change": script.get("status_change", []),
    }


def _summarize_result(result: dict) -> str:
    script = result.get("final_script", {}) or {}
    scenes = ensure_list(script.get("scenes"))
    scene_summary = " / ".join(
        scene.get("action", "") for scene in scenes[:3] if isinstance(scene, dict)
    )
    ending = script.get("ending_hook", "")
    return _compact_text([scene_summary, f"Ending hook: {ending}" if ending else ""])


def _compact_text(parts: list[object]) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _memory_result_from_chunk(chunk: KnowledgeChunk, score: float, retrieval: str) -> dict:
    return {
        "id": str(chunk.id),
        "chunk_type": chunk.chunk_type,
        "source": chunk.source,
        "text": chunk.text,
        "meta": chunk.meta or {},
        "score": score,
        "retrieval": retrieval,
    }


def _query_tokens(query: str) -> list[str]:
    raw_tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")
    seen: set[str] = set()
    tokens: list[str] = []
    for token in raw_tokens:
        normalized = token.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return tokens[:12]


def _fuse_memory_results(vector_results: list[dict], keyword_results: list[dict], limit: int) -> list[dict]:
    fused: dict[str, dict] = {}
    for source_name, results in (("vector", vector_results), ("keyword", keyword_results)):
        for rank, item in enumerate(results, start=1):
            key = item.get("id") or item.get("text", "")[:120]
            contribution = 1 / (60 + rank)
            if key not in fused:
                fused[key] = {**item, "score": 0.0, "retrieval_sources": []}
            fused[key]["score"] += contribution
            fused[key]["retrieval_sources"].append(source_name)
            if item.get("score", 0) > fused[key].get("raw_score", 0):
                fused[key]["raw_score"] = item.get("score", 0)
    results = sorted(
        fused.values(),
        key=lambda item: (item["score"], item.get("raw_score", 0)),
        reverse=True,
    )
    for item in results:
        sources = sorted(set(item.pop("retrieval_sources", [])))
        item["retrieval"] = "hybrid" if len(sources) > 1 else (sources[0] if sources else item["retrieval"])
        item["score"] = round(float(item["score"]), 4)
    return results[:limit]


def _safe_embed_text(text: str) -> list[float] | None:
    try:
        return bailian_embedding_client.embed_text(text)
    except Exception:
        return None


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


project_repository = ProjectRepository()
