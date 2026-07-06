from typing import Literal, TypedDict


Severity = Literal["PASS", "MINOR", "SEVERE", "FATAL"]
AgentMode = Literal["tool", "model", "hybrid"]
WorkflowStage = Literal[
    "orchestration",
    "world_building",
    "writing",
    "quality_review",
    "revision",
    "shot_directing",
    "done",
]


class ReviewFinding(TypedDict):
    severity: Severity
    category: str
    message: str
    target: str


class AgentTrace(TypedDict):
    agent: str
    summary: str


class ScriptState(TypedDict, total=False):
    project_id: str
    user_brief: str
    model: str
    agent_models: dict
    agent_modes: dict
    platform: str
    genre: str
    audience: str
    episode_count: int
    episode_number: int
    target_duration_sec: int
    fast_mode: bool
    stage: WorkflowStage
    revision_round: int
    max_revision_rounds: int
    planning_report: dict
    project_bible: dict
    episode_outline: dict
    draft_script: dict
    review_status: Severity
    review_findings: list[ReviewFinding]
    final_script: dict
    shooting_script: list[dict]
    mcp_context: dict
    memory_context: dict
    previous_episodes: list[dict]
    llm_warnings: list[str]
    workflow_error: str
    trace: list[AgentTrace]
