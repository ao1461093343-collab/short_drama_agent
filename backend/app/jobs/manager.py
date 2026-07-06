import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock
from typing import Literal
from uuid import uuid4

from app.graph.workflow import interactive_script_graph, script_graph
from app.graph.nodes.llm_helpers import ensure_dict, ensure_list
from app.projects.repository import project_repository


JobStatus = Literal["queued", "running", "waiting_human", "succeeded", "failed"]

NODE_LABELS = {
    "orchestrator": "统筹策划",
    "world_builder": "世界观构建",
    "lead_writer": "主笔编剧",
    "quality_review": "综合质检",
    "revision": "改写迭代",
    "shot_director": "分镜导演",
}
NODE_ORDER = ["统筹策划", "世界观构建", "主笔编剧", "综合质检", "改写迭代", "分镜导演"]


class JobManager:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, dict] = {}
        self._events: dict[str, Queue] = {}
        self._lock = Lock()

    def submit(self, initial_state: dict) -> dict:
        job_id = str(uuid4())
        now = self._now()
        human_review = bool(initial_state.get("human_review_enabled"))
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "progress": 0,
                "message": "Task submitted.",
                "current_agent": "",
                "logs": [],
                "result": None,
                "error": None,
                "interrupt": None,
                "human_review_enabled": human_review,
                "created_at": now,
                "updated_at": now,
            }
            self._events[job_id] = Queue()
        self._emit(job_id, "job", self.get(job_id))
        self._executor.submit(self._run, job_id, initial_state)
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def iter_events(self, job_id: str):
        queue = self._events.get(job_id)
        if queue is None:
            return
        job = self.get(job_id)
        if job:
            yield self._format_sse("job", job)
        while True:
            try:
                event_type, payload = queue.get(timeout=15)
            except Empty:
                yield self._format_sse("ping", {"time": self._now()})
                continue
            yield self._format_sse(event_type, payload)
            if event_type in {"result", "error"}:
                break

    def resume(self, job_id: str, changes: dict | None = None) -> dict:
        job = self.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job.get("status") != "waiting_human":
            return job

        self._update(
            job_id,
            status="running",
            interrupt=None,
            message="Human changes received. Resuming workflow.",
        )
        self._executor.submit(self._resume_after_human, job_id, changes or {})
        return self.get(job_id)

    def _run(self, job_id: str, initial_state: dict) -> None:
        self._update(job_id, status="running", progress=5, message="Multi-agent workflow running.")
        try:
            if initial_state.get("human_review_enabled"):
                result = self._run_interactive_until_interrupt(job_id, initial_state)
                if result is None:
                    return
            else:
                result = self._run_graph_with_progress(job_id, initial_state, script_graph, None)
            self._complete(job_id, result, initial_state)
        except Exception as exc:
            self._fail(job_id, exc)

    def _resume_after_human(self, job_id: str, changes: dict) -> None:
        job = self.get(job_id)
        if not job:
            return
        initial_state = job.get("initial_state", {})
        config = self._thread_config(job_id)
        try:
            current = interactive_script_graph.get_state(config).values or {}
            patched = self._apply_human_changes(current, changes)
            interactive_script_graph.update_state(config, patched, as_node="lead_writer")
            result = self._run_graph_with_progress(job_id, None, interactive_script_graph, config)
            self._complete(job_id, result, initial_state)
        except Exception as exc:
            self._fail(job_id, exc)

    def _run_interactive_until_interrupt(self, job_id: str, initial_state: dict) -> dict | None:
        config = self._thread_config(job_id)
        self._update(job_id, initial_state=initial_state)
        latest_state = self._run_graph_with_progress(job_id, initial_state, interactive_script_graph, config)
        snapshot = interactive_script_graph.get_state(config)
        if snapshot.next:
            interrupt_payload = self._build_interrupt_payload(snapshot.values or latest_state)
            self._update(
                job_id,
                status="waiting_human",
                progress=45,
                current_agent="人工确认",
                message="Draft outline is ready for human review.",
                interrupt=interrupt_payload,
            )
            self._emit(job_id, "interrupt", interrupt_payload)
            return None
        return latest_state

    def _run_graph_with_progress(self, job_id: str, graph_input, graph, config) -> dict:
        latest_state = graph_input or {}
        completed_nodes: list[str] = []
        kwargs = {"stream_mode": "updates"}
        if config:
            kwargs["config"] = config
        for update in graph.stream(graph_input, **kwargs):
            if not isinstance(update, dict):
                continue
            for node_name, node_state in update.items():
                if not isinstance(node_state, dict):
                    continue
                latest_state = node_state
                label = NODE_LABELS.get(node_name, node_name)
                completed_nodes.append(label)
                next_agent = self._next_agent_label(label)
                progress = min(95, 8 + len(completed_nodes) * 13)
                summary = self._node_summary(node_name, node_state)
                self._append_log(job_id, f"{label} done")
                if summary:
                    self._emit_tokens(job_id, label, summary)
                self._update(
                    job_id,
                    status="running",
                    progress=progress,
                    current_agent=next_agent or label,
                    message=(
                        f"{label} completed. Running {next_agent}."
                        if next_agent
                        else f"{label} completed. Finalizing."
                    ),
                )
        return latest_state

    def _complete(self, job_id: str, result: dict, initial_state: dict) -> None:
        result["project_id"] = initial_state.get("project_id")
        result["user_brief"] = initial_state.get("user_brief")
        result["platform"] = initial_state.get("platform")
        result["genre"] = initial_state.get("genre")
        result["episode_number"] = initial_state.get("episode_number")
        result["model"] = initial_state.get("model")
        result["agent_models"] = initial_state.get("agent_models", {})
        result["agent_modes"] = initial_state.get("agent_modes", {})
        saved = project_repository.save_version(
            initial_state.get("project_id"),
            result,
            result.get("final_script", {}).get("title"),
        )
        result["saved_project_id"] = saved["project"]["id"]
        result["saved_version_id"] = saved["version"]["id"]
        self._update(
            job_id,
            status="succeeded",
            progress=100,
            current_agent="",
            message="Generation complete.",
            result=result,
        )
        self._emit(job_id, "result", result)

    def _fail(self, job_id: str, exc: Exception) -> None:
        payload = {"error": str(exc)}
        self._update(
            job_id,
            status="failed",
            progress=100,
            message="Generation failed.",
            error=str(exc),
        )
        self._emit(job_id, "error", payload)

    def _append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            logs = self._jobs[job_id].setdefault("logs", [])
            logs.append({"time": self._now(), "message": message})
            self._jobs[job_id]["logs"] = logs[-30:]
            self._jobs[job_id]["updated_at"] = self._now()

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(changes)
            self._jobs[job_id]["updated_at"] = self._now()
            snapshot = dict(self._jobs[job_id])
        self._emit(job_id, "job", snapshot)

    def _emit_tokens(self, job_id: str, label: str, text: str) -> None:
        for chunk in self._chunk_text(text):
            self._emit(job_id, "token", {"agent": label, "text": chunk})

    def _emit(self, job_id: str, event_type: str, payload: dict | None) -> None:
        queue = self._events.get(job_id)
        if queue is not None:
            queue.put((event_type, payload or {}))

    @staticmethod
    def _format_sse(event_type: str, payload: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _chunk_text(text: str, size: int = 18) -> list[str]:
        clean = " ".join(str(text or "").split())
        return [clean[index : index + size] for index in range(0, len(clean), size)]

    @staticmethod
    def _node_summary(node_name: str, state: dict) -> str:
        if node_name == "orchestrator":
            report = ensure_dict(state.get("planning_report"))
            return " / ".join(str(item) for item in ensure_list(report.get("creative_strategy"))[:3])
        if node_name == "world_builder":
            bible = ensure_dict(state.get("project_bible"))
            return str(bible.get("logline") or bible.get("theme") or "")
        if node_name == "lead_writer":
            outline = ensure_dict(state.get("episode_outline"))
            script = ensure_dict(state.get("draft_script"))
            return " ".join(
                [
                    str(outline.get("title") or script.get("title") or ""),
                    " ".join(str(item) for item in ensure_list(outline.get("beats"))[:4]),
                ]
            )
        if node_name == "quality_review":
            return f"Review status: {state.get('review_status', 'PASS')}"
        if node_name == "revision":
            return "Revision completed."
        if node_name == "shot_director":
            return "Shot table completed."
        return ""

    @staticmethod
    def _build_interrupt_payload(state: dict) -> dict:
        return {
            "node": "lead_writer",
            "title": "Draft outline review",
            "episode_outline": state.get("episode_outline", {}),
            "draft_script": state.get("draft_script", {}),
            "message": "Edit the outline or draft, then resume the workflow.",
        }

    @staticmethod
    def _apply_human_changes(state: dict, changes: dict) -> dict:
        patched = dict(state)
        if isinstance(changes.get("episode_outline"), dict):
            patched["episode_outline"] = changes["episode_outline"]
        if isinstance(changes.get("draft_script"), dict):
            patched["draft_script"] = changes["draft_script"]
        notes = changes.get("human_notes")
        if notes:
            patched["human_notes"] = notes
        return patched

    @staticmethod
    def _thread_config(job_id: str) -> dict:
        return {"configurable": {"thread_id": job_id}}

    @staticmethod
    def _next_agent_label(label: str) -> str:
        if label not in NODE_ORDER:
            return ""
        index = NODE_ORDER.index(label)
        return NODE_ORDER[index + 1] if index + 1 < len(NODE_ORDER) else ""

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


job_manager = JobManager()
