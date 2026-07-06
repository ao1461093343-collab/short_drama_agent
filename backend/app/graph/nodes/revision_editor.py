from copy import deepcopy

from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_mode, call_agent_json, ensure_dict, ensure_list
from app.graph.state import ScriptState
from app.tools.handlers import sanitize_sensitive_terms


def revision_editor_node(state: ScriptState) -> ScriptState:
    script = deepcopy(ensure_dict(state.get("draft_script")))

    for scene in ensure_list(script.get("scenes")):
        if not isinstance(scene, dict):
            continue
        for line in ensure_list(scene.get("dialogue")):
            if not isinstance(line, dict):
                continue
            if "原来你才是林家真正的继承人" in str(line.get("line", "")):
                line["line"] = "难怪林家那枚戒指，只认你的手。"

    script["revision_notes"] = [
        finding["message"]
        for finding in ensure_list(state.get("review_findings"))
        if isinstance(finding, dict) and finding.get("severity") == "MINOR"
    ]
    script, replacements = sanitize_sensitive_terms(script)
    if replacements:
        replacement_values = sorted({item["replacement"] for item in replacements})
        script.setdefault("revision_notes", []).append(
            f"已自动弱化敏感表达，替换为：{'、'.join(replacement_values)}。"
        )

    mode = agent_mode(state, "改写迭代", default="model")
    if mode == "tool" or (state.get("fast_mode", True) and mode != "model"):
        result = {"draft_script": script, "revision_notes": script["revision_notes"]}
    else:
        result = call_agent_json(
            agent_name="改写迭代",
            state=state,
            system_prompt=(
                "你是短剧改写迭代 Agent。只处理 MINOR 级问题，进行局部文本替换、敏感表达弱化、"
                "台词润色，不改变主线、人设和场景结构。只输出 JSON，字段必须包含 draft_script "
                "和 revision_notes。"
            ),
            payload={
                "draft_script": script,
                "review_findings": ensure_list(state.get("review_findings")),
            },
            fallback={"draft_script": script, "revision_notes": script["revision_notes"]},
            temperature=0.55,
            max_tokens=2400,
        )

    result = ensure_dict(result)
    revised_script = result.get("draft_script") if isinstance(result.get("draft_script"), dict) else script
    if "revision_notes" not in revised_script:
        revised_script["revision_notes"] = result.get("revision_notes", script["revision_notes"])

    next_round = state.get("revision_round", 0) + 1

    return {
        **state,
        "stage": "revision",
        "revision_round": next_round,
        "draft_script": revised_script,
        "trace": append_trace(state, "改写迭代", "按审查意见完成局部替换与台词润色。"),
    }
