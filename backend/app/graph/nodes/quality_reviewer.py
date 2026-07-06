from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_mode, call_agent_json, ensure_dict
from app.graph.state import ReviewFinding, ScriptState
from app.tools.handlers import (
    analyze_script_density,
    calculate_script_runtime,
    sanitize_sensitive_terms,
    scan_sensitive_terms,
)


def _highest_status(findings: list[ReviewFinding]) -> str:
    priority = {"FATAL": 4, "SEVERE": 3, "MINOR": 2, "PASS": 1}
    status = "PASS"
    for finding in findings:
        severity = finding.get("severity", "PASS")
        if severity in priority and priority[severity] > priority[status]:
            status = severity
    return status


def quality_reviewer_node(state: ScriptState) -> ScriptState:
    round_no = state.get("revision_round", 0)
    script = ensure_dict(state.get("draft_script"))
    script_text = str(script)
    sensitive_result = scan_sensitive_terms(script_text)
    runtime_result = calculate_script_runtime(script.get("scenes", []))
    density_result = analyze_script_density(script.get("scenes", []))

    fallback_findings: list[ReviewFinding] = []
    if round_no == 0 and "真正的继承人" in str(script):
        fallback_findings.append(
            {
                "severity": "MINOR",
                "category": "台词瑕疵",
                "message": "“真正的继承人”表达略直白，建议改成更有短剧张力的揭示。",
                "target": "scene_3.dialogue",
            }
        )
    for match in sensitive_result["matches"]:
        fallback_findings.append(
            {
                "severity": match["level"],
                "category": "平台敏感词",
                "message": f"发现“{match['term']}”：{match['suggestion']}",
                "target": "draft_script",
            }
        )

    target_duration = state.get("target_duration_sec")
    if isinstance(target_duration, int) and runtime_result["total_duration_sec"] > target_duration + 30:
        fallback_findings.append(
            {
                "severity": "SEVERE",
                "category": "节奏时长",
                "message": f"当前估算 {runtime_result['total_duration_sec']} 秒，明显超过目标时长。",
                "target": "draft_script.scenes",
            }
        )

    if density_result["total_dialogue_lines"] < 12:
        fallback_findings.append(
            {
                "severity": "SEVERE",
                "category": "内容密度",
                "message": (
                    f"当前仅 {density_result['total_dialogue_lines']} 句台词，单集内容偏短。"
                    "建议扩展到至少 12 句台词，并补足压迫、反击、反转和结尾钩子。"
                ),
                "target": "draft_script.scenes.dialogue",
            }
        )
    if density_result["sparse_scene_count"] >= 2:
        fallback_findings.append(
            {
                "severity": "SEVERE",
                "category": "场景碎片化",
                "message": (
                    f"有 {density_result['sparse_scene_count']} 个场景只有 0-1 句台词，像是一句台词换一次场景。"
                    "场景应代表连续时间地点，同一对峙段落应留在同一场景内。"
                ),
                "target": "draft_script.scenes",
            }
        )

    if state.get("force_review_status"):
        forced = state["force_review_status"]
        fallback_findings.append(
            {
                "severity": forced,
                "category": "调试注入",
                "message": f"人为指定审查等级：{forced}",
                "target": "workflow",
            }
        )

    fallback = {
        "status": _highest_status(fallback_findings),
        "findings": fallback_findings,
        "summary": "完成连贯性与合规双重审查。",
    }

    mode = agent_mode(state, "综合质检", default="hybrid")
    if mode == "tool" or (state.get("fast_mode", True) and mode != "model"):
        result = fallback
    else:
        result = call_agent_json(
            agent_name="综合质检",
            state=state,
            system_prompt=(
                "你是短剧综合质检 Agent，负责连贯性和合规双重审查。必须按严重等级输出："
                "FATAL=吃书/人设主线严重冲突，SEVERE=节奏断裂或关键剧情无法成立，"
                "MINOR=轻微敏感词、台词瑕疵、表达直白，PASS=零修改。"
                "只输出 JSON，字段必须包含 status, findings, summary。findings 中每项包含 "
                "severity, category, message, target。"
            ),
            payload={
                "project_bible": state.get("project_bible"),
                "episode_outline": state.get("episode_outline"),
                "draft_script": script,
                "revision_round": round_no,
                "tool_results": {
                    "sensitive_terms": sensitive_result,
                    "runtime": runtime_result,
                    "density": density_result,
                },
            },
            fallback=fallback,
            temperature=0.2,
            max_tokens=1600,
        )

    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    normalized_findings: list[ReviewFinding] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = finding.get("severity", "MINOR")
        if severity not in {"PASS", "MINOR", "SEVERE", "FATAL"}:
            severity = "MINOR"
        if severity == "PASS":
            continue
        normalized_findings.append(
            {
                "severity": severity,
                "category": str(finding.get("category", "未分类")),
                "message": str(finding.get("message", "")),
                "target": str(finding.get("target", "draft_script")),
            }
        )

    status = result.get("status")
    if status not in {"PASS", "MINOR", "SEVERE", "FATAL"}:
        status = _highest_status(normalized_findings)
    if not normalized_findings:
        status = "PASS"

    final_script = script if status == "PASS" else state.get("final_script", {})
    workflow_error = state.get("workflow_error") or ""
    trace_message = f"完成连贯性与合规审查，结果为 {status}。"

    max_rounds_reached = state.get("revision_round", 0) >= state.get("max_revision_rounds", 3)
    only_minor = status == "MINOR" and all(
        finding.get("severity") == "MINOR" for finding in normalized_findings
    )
    if max_rounds_reached and only_minor:
        sanitized_script, replacements = sanitize_sensitive_terms(script)
        status = "PASS"
        final_script = sanitized_script
        workflow_error = ""
        normalized_findings = []
        if replacements:
            trace_message = "仅剩 MINOR 问题，已自动弱化敏感表达并放行生成分镜。"
        else:
            trace_message = "仅剩 MINOR 问题，已按最大审改轮次策略放行生成分镜。"

    return {
        **state,
        "stage": "quality_review",
        "review_status": status,
        "review_findings": normalized_findings,
        "workflow_error": (
            "达到最大审改轮次，仍未通过质检。"
            if status != "PASS" and state.get("revision_round", 0) >= state.get("max_revision_rounds", 3)
            else workflow_error
        ),
        "final_script": final_script,
        "trace": append_trace(state, "综合质检", trace_message),
    }
