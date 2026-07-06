from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_mode, call_agent_json, ensure_dict, ensure_list
from app.graph.state import ScriptState
from app.tools.handlers import build_shot_table


def shot_director_node(state: ScriptState) -> ScriptState:
    script = ensure_dict(state.get("final_script")) or ensure_dict(state.get("draft_script"))
    shooting_script = build_shot_table(ensure_list(script.get("scenes")))["shooting_script"]
    mode = agent_mode(state, "分镜导演", default="tool")

    if mode in {"model", "hybrid"}:
        result = call_agent_json(
            agent_name="分镜导演",
            state=state,
            system_prompt=(
                "你是短剧分镜导演 Agent。剧本已经定稿，请拆解为可执行的表格化拍摄分镜。"
                "每行必须包含 镜号, 场景, 画面, 台词, 时长, 机位建议, 表演重点。"
                "混合模式下可以基于工具生成的初始分镜进一步细化，不要改变定稿剧情。"
                "只输出 JSON，字段必须包含 shooting_script。"
            ),
            payload={
                "final_script": script,
                "tool_shot_table": shooting_script,
                "platform": state.get("platform"),
                "target_duration_sec": state.get("target_duration_sec"),
            },
            fallback={"shooting_script": shooting_script},
            temperature=0.35,
            max_tokens=2400,
        )
        result = ensure_dict(result)
        if isinstance(result.get("shooting_script"), list):
            shooting_script = result["shooting_script"]

    return {
        **state,
        "stage": "done",
        "final_script": script,
        "shooting_script": shooting_script,
        "trace": append_trace(state, "分镜导演", "剧本定稿后拆解为表格化拍摄分镜。"),
    }
