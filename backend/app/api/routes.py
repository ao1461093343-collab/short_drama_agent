from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.models import BAILIAN_MODEL_PRESETS, DEFAULT_BAILIAN_MODEL
from app.exporters.script_exporter import export_script_docx, export_script_pdf
from app.graph.nodes.llm_helpers import call_agent_json
from app.graph.workflow import script_graph
from app.jobs.manager import job_manager
from app.memory.indexer import memory_indexer
from app.projects.repository import project_repository
from app.tools.handlers import build_shot_table
from app.tools.function_schemas import SCRIPT_TOOLS

router = APIRouter()

AGENT_NAMES = ["统筹策划", "世界观构建", "主笔编剧", "综合质检", "改写迭代", "分镜导演"]
DEFAULT_AGENT_MODES = {
    "统筹策划": "hybrid",
    "世界观构建": "model",
    "主笔编剧": "model",
    "综合质检": "hybrid",
    "改写迭代": "model",
    "分镜导演": "tool",
}

TOOL_LABELS = {
    "scan_sensitive_terms": ("敏感词扫描", "扫描平台敏感词和风险表达"),
    "calculate_script_runtime": ("时长统计", "统计分场时长并检查是否超过目标"),
    "analyze_script_density": ("剧本密度检查", "检查台词数量和碎片化换场问题"),
    "classify_review_findings": ("审查等级归并", "按问题严重度得出最高审查等级"),
    "replace_dialogue_line": ("台词局部替换", "按审查意见替换指定台词"),
    "sanitize_sensitive_terms": ("敏感表达弱化", "确定性替换平台敏感或过强表达"),
    "build_shot_table": ("分镜表生成", "把定稿场景转换为拍摄分镜表"),
}


class CreateScriptRequest(BaseModel):
    project_id: str | None = None
    user_brief: str = Field(..., min_length=2)
    model: str = DEFAULT_BAILIAN_MODEL
    agent_models: dict[str, str] = Field(default_factory=dict)
    agent_modes: dict[str, str] = Field(default_factory=dict)
    platform: str = "抖音"
    genre: str = "都市情感反转"
    audience: str = "18-35 岁短视频用户"
    episode_count: int = 12
    episode_number: int | None = None
    target_duration_sec: int = 90
    fast_mode: bool = True
    human_review_enabled: bool = False
    previous_episodes: list[dict] = Field(default_factory=list)


class ExportScriptRequest(BaseModel):
    result: dict


class CreateProjectRequest(BaseModel):
    title: str
    platform: str = "抖音"
    genre: str = "都市情感反转"
    brief: str = ""


class SaveVersionRequest(BaseModel):
    project_id: str | None = None
    title: str | None = None
    result: dict


class ResumeJobRequest(BaseModel):
    episode_outline: dict | None = None
    draft_script: dict | None = None
    human_notes: str | None = None


class RewriteRequest(BaseModel):
    result: dict
    model: str = DEFAULT_BAILIAN_MODEL
    agent_models: dict[str, str] = Field(default_factory=dict)
    instruction: str | None = None


class RewriteHookRequest(RewriteRequest):
    hook_3s: str


class RewriteSceneRequest(RewriteRequest):
    scene: dict


class RewriteDialogueRequest(RewriteRequest):
    dialogue: dict
    scene: dict | None = None


def _build_initial_state(payload: CreateScriptRequest) -> dict:
    previous_episodes = payload.previous_episodes or project_repository.previous_episodes(payload.project_id)
    project = project_repository.get_project(payload.project_id) if payload.project_id else None
    project_bible = _project_bible(project)
    episode_number = max(int(payload.episode_number or 0), _next_episode_number(previous_episodes))
    return {
        "project_id": payload.project_id or str(uuid4()),
        "user_brief": payload.user_brief,
        "model": payload.model,
        "agent_models": payload.agent_models,
        "agent_modes": _normalize_agent_modes(payload.agent_modes),
        "platform": payload.platform,
        "genre": payload.genre,
        "audience": payload.audience,
        "episode_count": payload.episode_count,
        "episode_number": episode_number,
        "target_duration_sec": payload.target_duration_sec,
        "fast_mode": payload.fast_mode,
        "human_review_enabled": payload.human_review_enabled,
        "previous_episodes": previous_episodes,
        "project_bible": project_bible,
        "revision_round": 0,
        "max_revision_rounds": 3,
        "llm_warnings": [],
        "trace": [],
    }


def _project_bible(project: dict | None) -> dict:
    if not project:
        return {}
    if isinstance(project.get("bible"), dict) and project["bible"]:
        return project["bible"]
    for version in project.get("versions", []):
        bible = version.get("result", {}).get("project_bible")
        if isinstance(bible, dict) and bible:
            return bible
    return {}


def _next_episode_number(previous_episodes: list[dict]) -> int:
    numbers = [
        int(item.get("episode"))
        for item in previous_episodes
        if isinstance(item, dict) and str(item.get("episode", "")).isdigit()
    ]
    return (max(numbers) + 1) if numbers else 1


def _normalize_agent_modes(agent_modes: dict[str, str] | None) -> dict[str, str]:
    normalized = DEFAULT_AGENT_MODES.copy()
    for agent_name, mode in (agent_modes or {}).items():
        if agent_name in AGENT_NAMES and mode in {"tool", "model", "hybrid"}:
            normalized[agent_name] = mode
    return normalized


def _rewrite_state(payload: RewriteRequest) -> dict:
    return {
        "model": payload.model,
        "agent_models": payload.agent_models,
        "llm_warnings": [],
        "trace": [],
    }


@router.post("/scripts/create")
def create_script(payload: CreateScriptRequest) -> dict:
    initial_state = _build_initial_state(payload)
    try:
        result = script_graph.invoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/scripts/jobs")
def create_script_job(payload: CreateScriptRequest) -> dict:
    return job_manager.submit(_build_initial_state(payload))


@router.get("/scripts/jobs/{job_id}")
def get_script_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return job


@router.get("/scripts/jobs/{job_id}/events")
def stream_script_job(job_id: str):
    if not job_manager.get(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        job_manager.iter_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/scripts/jobs/{job_id}/resume")
def resume_script_job(job_id: str, payload: ResumeJobRequest) -> dict:
    try:
        return job_manager.resume(job_id, payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.post("/scripts/export/docx")
def export_docx(payload: ExportScriptRequest, background_tasks: BackgroundTasks):
    path = export_script_docx(payload.result)
    background_tasks.add_task(_delete_file, path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="短剧剧本.docx",
        background=background_tasks,
    )


@router.post("/scripts/export/pdf")
def export_pdf(payload: ExportScriptRequest, background_tasks: BackgroundTasks):
    path = export_script_pdf(payload.result)
    background_tasks.add_task(_delete_file, path)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="短剧剧本.pdf",
        background=background_tasks,
    )


def _delete_file(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


@router.post("/scripts/rewrite/hook")
def rewrite_hook(payload: RewriteHookRequest) -> dict:
    fallback = {
        "hook_3s": payload.hook_3s.strip() or "她抬眼看向镜头：今天，我把真相还给所有人。",
        "rewrite_notes": ["保留原设定，强化前三秒冲突。"],
    }
    state = _rewrite_state(payload)
    result = call_agent_json(
        agent_name="改写迭代",
        state=state,
        system_prompt=(
            "你是短剧前三秒钩子强化 Agent。只改写 hook_3s，不改主线和人物关系。"
            "输出要短、狠、可拍，适合竖屏开场。只输出 JSON，字段必须包含 hook_3s 和 rewrite_notes。"
        ),
        payload={
            "current_hook_3s": payload.hook_3s,
            "instruction": payload.instruction,
            "project_bible": payload.result.get("project_bible"),
            "final_script": payload.result.get("final_script"),
        },
        fallback=fallback,
        temperature=0.65,
        max_tokens=1000,
    )
    return {"hook_3s": result.get("hook_3s", fallback["hook_3s"]), "warnings": state.get("llm_warnings", [])}


@router.post("/scripts/rewrite/scene")
def rewrite_scene(payload: RewriteSceneRequest) -> dict:
    fallback = {
        "scene": payload.scene,
        "rewrite_notes": ["已保留场景结构，等待模型可用后进行精修。"],
    }
    state = _rewrite_state(payload)
    result = call_agent_json(
        agent_name="改写迭代",
        state=state,
        system_prompt=(
            "你是短剧场景润色 Agent。只优化给定 scene 的 action、duration_sec 和 dialogue，"
            "不要新增主线设定，不要改 scene_no。只输出 JSON，字段必须包含 scene 和 rewrite_notes。"
        ),
        payload={
            "scene": payload.scene,
            "instruction": payload.instruction,
            "project_bible": payload.result.get("project_bible"),
            "final_script_summary": {
                "title": payload.result.get("final_script", {}).get("title"),
                "hook_3s": payload.result.get("final_script", {}).get("hook_3s"),
                "ending_hook": payload.result.get("final_script", {}).get("ending_hook"),
            },
        },
        fallback=fallback,
        temperature=0.6,
        max_tokens=1800,
    )
    scene = result.get("scene") if isinstance(result.get("scene"), dict) else payload.scene
    scene["scene_no"] = payload.scene.get("scene_no")
    return {"scene": scene, "warnings": state.get("llm_warnings", [])}


@router.post("/scripts/rewrite/dialogue")
def rewrite_dialogue(payload: RewriteDialogueRequest) -> dict:
    fallback = {
        "dialogue": payload.dialogue,
        "rewrite_notes": ["已保留原台词，等待模型可用后进行精修。"],
    }
    state = _rewrite_state(payload)
    result = call_agent_json(
        agent_name="改写迭代",
        state=state,
        system_prompt=(
            "你是短剧台词改写 Agent。只改写给定 dialogue.line，可以微调 speaker 但不要改变说话人身份。"
            "台词必须短、有情绪推进、适合口播。只输出 JSON，字段必须包含 dialogue 和 rewrite_notes。"
        ),
        payload={
            "dialogue": payload.dialogue,
            "scene": payload.scene,
            "instruction": payload.instruction,
            "project_bible": payload.result.get("project_bible"),
        },
        fallback=fallback,
        temperature=0.65,
        max_tokens=800,
    )
    dialogue = result.get("dialogue") if isinstance(result.get("dialogue"), dict) else payload.dialogue
    return {"dialogue": dialogue, "warnings": state.get("llm_warnings", [])}


@router.post("/scripts/rebuild-shots")
def rebuild_shots(payload: ExportScriptRequest) -> dict:
    scenes = payload.result.get("final_script", {}).get("scenes", [])
    return build_shot_table(scenes)


@router.get("/projects")
def list_projects() -> dict:
    return {"projects": project_repository.list_projects()}


@router.post("/projects")
def create_project(payload: CreateProjectRequest) -> dict:
    return project_repository.create_project(payload.title, payload.platform, payload.genre, payload.brief)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    project = project_repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    if not project_repository.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": True, "project_id": project_id}


@router.delete("/projects/{project_id}/versions/{version_id}")
def delete_project_version(project_id: str, version_id: str) -> dict:
    if not project_repository.delete_version(project_id, version_id):
        raise HTTPException(status_code=404, detail="Version not found")
    return {"deleted": True, "project_id": project_id, "version_id": version_id}


@router.post("/projects/save-version")
def save_project_version(payload: SaveVersionRequest) -> dict:
    return project_repository.save_version(payload.project_id, payload.result, payload.title)


@router.get("/models")
def list_models() -> dict:
    return {
        "default": DEFAULT_BAILIAN_MODEL,
        "custom_model_allowed": True,
        "custom_model_note": "Any DashScope Bailian OpenAI-compatible model id can be submitted.",
        "models": [
            {"name": name, **metadata}
            for name, metadata in BAILIAN_MODEL_PRESETS.items()
        ],
        "agent_defaults": {
            agent: {
                "mode": DEFAULT_AGENT_MODES[agent],
                "model": "",
            }
            for agent in AGENT_NAMES
        },
    }


@router.get("/capabilities")
def list_capabilities() -> dict:
    return {
        "function_tools": [
            {
                "name": tool["function"]["name"],
                "label": TOOL_LABELS.get(tool["function"]["name"], (tool["function"]["name"], ""))[0],
                "description": TOOL_LABELS.get(
                    tool["function"]["name"],
                    (tool["function"]["name"], tool["function"]["description"]),
                )[1],
            }
            for tool in SCRIPT_TOOLS
        ],
        "mcp_context_sources": [
            "script_templates",
            "platform_rules",
            "example_cases",
        ],
        "agents": [
            {
                "name": agent,
                "default_mode": DEFAULT_AGENT_MODES[agent],
                "model_configurable": True,
            }
            for agent in AGENT_NAMES
        ],
        "agent_modes": [
            {"value": "tool", "label": "工具模式", "description": "优先使用本地规则、MCP 上下文和 Function Calling 工具，速度快且稳定。"},
            {"value": "model", "label": "模型模式", "description": "直接调用百炼模型，创造力更强，耗时更长。"},
            {"value": "hybrid", "label": "混合模式", "description": "先用工具产出结构化依据，再交给模型判断或润色。"},
        ],
        "memory_strategy": {
            "series_memory": "项目 logline、主题、主线与创作规则",
            "character_memory": "角色身份、欲望与当前状态",
            "episode_memory": "最近 5 集摘要、结尾钩子和状态变化",
            "open_threads": "未闭合悬念，用于续集回收",
            "vector_memory": "PostgreSQL + pgvector 真实检索项目历史片段，并注入下一集创作上下文",
            "hybrid_retrieval": "向量召回 + 关键词召回后用 RRF 融合去重",
        },
        "memory_architecture": [
            {
                "layer": "working_context",
                "role": "当前 LangGraph state，保存本轮需求、Agent trace、审查结果和人工修改。",
            },
            {
                "layer": "series_state",
                "role": "项目圣经、角色状态、主线规则，作为每集生成的稳定约束。",
            },
            {
                "layer": "episodic_memory",
                "role": "每集定稿后切成 episode summary、open thread、character delta、scene memory。",
            },
            {
                "layer": "hybrid_retrieval",
                "role": "生成新集时按项目 ID 做向量召回 + 关键词召回，用 RRF 融合后注入 prompt。",
            },
            {
                "layer": "async_indexing",
                "role": "保存版本只写 pending chunks，后台队列慢慢补 BGE-M3 embedding，避免阻塞创作链路。",
            },
        ],
        "workflow": {
            "events": "SSE stream at /api/scripts/jobs/{job_id}/events",
            "human_checkpoint": "Optional pause after lead writer outline via human_review_enabled",
            "resume": "POST /api/scripts/jobs/{job_id}/resume",
        },
        "storage": project_repository.storage_status(),
        "memory_indexer": memory_indexer.status(),
    }


@router.get("/memory/indexer")
def memory_indexer_status() -> dict:
    return memory_indexer.status()


@router.post("/memory/indexer/enqueue-pending")
def enqueue_pending_memory() -> dict:
    count = memory_indexer.enqueue_pending(limit=200)
    return {"queued": count, "status": memory_indexer.status()}
