from copy import deepcopy
from typing import Any, Callable


SENSITIVE_TERMS = {
    "绝对": "替换为更克制表达，避免绝对化承诺。",
    "包治": "涉及虚假疗效承诺，建议删除或剧情化处理。",
    "稳赚": "涉及收益承诺，建议改成不确定表达。",
    "弄死": "暴力表达过强，建议弱化为情绪台词。",
}

SENSITIVE_REPLACEMENTS = {
    "绝对": "尽量",
    "包治": "尝试缓解",
    "稳赚": "更有机会",
    "弄死": "让他付出代价",
}


def scan_sensitive_terms(text: str) -> dict:
    matches = [
        {"term": term, "level": "MINOR", "suggestion": suggestion}
        for term, suggestion in SENSITIVE_TERMS.items()
        if term in text
    ]
    return {"matches": matches, "count": len(matches)}


def sanitize_sensitive_terms(value):
    if isinstance(value, str):
        sanitized = value
        replacements = []
        for term, replacement in SENSITIVE_REPLACEMENTS.items():
            if term in sanitized:
                sanitized = sanitized.replace(term, replacement)
                replacements.append({"term": term, "replacement": replacement})
        return sanitized, replacements
    if isinstance(value, list):
        next_items = []
        replacements = []
        for item in value:
            sanitized_item, item_replacements = sanitize_sensitive_terms(item)
            next_items.append(sanitized_item)
            replacements.extend(item_replacements)
        return next_items, replacements
    if isinstance(value, dict):
        next_item = {}
        replacements = []
        for key, item in value.items():
            sanitized_item, item_replacements = sanitize_sensitive_terms(item)
            next_item[key] = sanitized_item
            replacements.extend(item_replacements)
        return next_item, replacements
    return value, []


def sanitize_sensitive_terms_tool(value) -> dict:
    sanitized, replacements = sanitize_sensitive_terms(value)
    return {"value": sanitized, "replacements": replacements}


def calculate_script_runtime(scenes: list[dict]) -> dict:
    total = 0
    missing = []
    for scene in scenes:
        if not isinstance(scene, dict):
            missing.append(None)
            continue
        duration = scene.get("duration_sec")
        if isinstance(duration, int):
            total += duration
        else:
            missing.append(scene.get("scene_no"))
    return {"total_duration_sec": total, "missing_scene_no": missing}


def analyze_script_density(scenes: list[dict]) -> dict:
    scene_count = 0
    dialogue_counts = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_count += 1
        dialogue = scene.get("dialogue", [])
        count = len([line for line in dialogue if isinstance(line, dict) and str(line.get("line", "")).strip()])
        dialogue_counts.append(count)

    total_dialogue_lines = sum(dialogue_counts)
    sparse_scene_count = sum(1 for count in dialogue_counts if count <= 1)
    short_scene_count = sum(1 for count in dialogue_counts if count < 3)
    return {
        "scene_count": scene_count,
        "total_dialogue_lines": total_dialogue_lines,
        "dialogue_counts": dialogue_counts,
        "sparse_scene_count": sparse_scene_count,
        "short_scene_count": short_scene_count,
        "average_dialogue_per_scene": round(total_dialogue_lines / scene_count, 2) if scene_count else 0,
    }


def classify_review_findings(findings: list[dict]) -> dict:
    priority = {"PASS": 1, "MINOR": 2, "SEVERE": 3, "FATAL": 4}
    status = "PASS"
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = finding.get("severity", "PASS")
        if severity in priority and priority[severity] > priority[status]:
            status = severity
    return {"status": status}


def replace_dialogue_line(
    script: dict,
    scene_no: int,
    speaker: str,
    old_line: str,
    new_line: str,
) -> dict:
    revised = deepcopy(script)
    replacements = 0
    if not isinstance(revised, dict):
        return {"script": script, "replacements": replacements}
    for scene in revised.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        if scene.get("scene_no") != scene_no:
            continue
        for dialogue in scene.get("dialogue", []):
            if not isinstance(dialogue, dict):
                continue
            if dialogue.get("speaker") == speaker and dialogue.get("line") == old_line:
                dialogue["line"] = new_line
                replacements += 1
    return {"script": revised, "replacements": replacements}


def build_shot_table(scenes: list[dict]) -> dict:
    rows = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        dialogue = [
            item.get("line", "")
            for item in scene.get("dialogue", [])
            if isinstance(item, dict)
        ]
        rows.append(
            {
                "镜号": f"{scene.get('scene_no', len(rows) + 1)}-1",
                "场景": scene.get("location", "待定"),
                "画面": scene.get("action", ""),
                "台词": " / ".join(dialogue),
                "时长": f"{scene.get('duration_sec', 0)}s",
                "机位建议": "竖屏中近景，关键情绪切特写",
                "表演重点": "压住节奏，在反转台词前留停顿",
            }
        )
    return {"shooting_script": rows}


TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "scan_sensitive_terms": scan_sensitive_terms,
    "calculate_script_runtime": calculate_script_runtime,
    "analyze_script_density": analyze_script_density,
    "classify_review_findings": classify_review_findings,
    "replace_dialogue_line": replace_dialogue_line,
    "build_shot_table": build_shot_table,
    "sanitize_sensitive_terms": sanitize_sensitive_terms_tool,
}


def call_tool(name: str, arguments: dict[str, Any]) -> dict:
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    return TOOL_REGISTRY[name](**arguments)
