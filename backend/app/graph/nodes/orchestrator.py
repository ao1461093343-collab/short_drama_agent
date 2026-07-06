from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_uses_model, call_agent_json
from app.graph.state import ScriptState
from app.mcp_client.client import script_mcp_client


def orchestrator_node(state: ScriptState) -> ScriptState:
    brief = state["user_brief"]
    platform = state.get("platform") or "抖音"
    genre = state.get("genre") or "都市情感反转"
    mcp_context = script_mcp_client.get_context_bundle(brief, platform)

    planning_report = {
        "agent": "统筹策划",
        "clarified_goal": brief,
        "model": state.get("model"),
        "mode": state.get("agent_modes", {}).get("统筹策划", "hybrid"),
        "platform": platform,
        "genre": genre,
        "audience": state.get("audience") or "18-35 岁短视频用户",
        "creative_strategy": [
            "前三秒抛出强冲突或身份错位",
            "每 30-45 秒安排一次信息翻转",
            "结尾保留下一集追看钩子",
        ],
        "platform_notes": [
            "节奏短平快，避免长篇背景交代",
            "台词适合竖屏短视频表演",
            "冲突明确，但避免低俗与极端表达",
        ],
    }

    if agent_uses_model(state, "统筹策划", default="hybrid"):
        planning_report = call_agent_json(
            agent_name="统筹策划",
            state=state,
            system_prompt=(
                "你是短剧统筹策划 Agent，负责需求澄清、题材定位、平台分析和创作策略。"
                "请结合 MCP 上下文输出结构化策划报告。只输出 JSON，字段必须包含 agent, "
                "clarified_goal, platform, genre, audience, creative_strategy, platform_notes。"
            ),
            payload={
                "user_brief": brief,
                "platform": platform,
                "genre": genre,
                "audience": state.get("audience"),
                "mcp_context": mcp_context,
                "target_duration_sec": state.get("target_duration_sec"),
                "episode_count": state.get("episode_count"),
            },
            fallback=planning_report,
            temperature=0.45,
            max_tokens=1800,
        )

    return {
        **state,
        "platform": platform,
        "genre": genre,
        "audience": planning_report["audience"],
        "stage": "orchestration",
        "revision_round": state.get("revision_round", 0),
        "max_revision_rounds": state.get("max_revision_rounds", 3),
        "mcp_context": mcp_context,
        "planning_report": planning_report,
        "trace": append_trace(state, "统筹策划", "完成需求澄清、题材定位与平台策略分析。"),
    }
