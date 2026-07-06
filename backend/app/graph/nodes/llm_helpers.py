import json
from typing import Any

from app.core.config import settings
from app.llm.bailian_client import BailianResponseError, bailian_chat_client


def wants_mock() -> bool:
    return settings.use_mock_llm


def agent_mode(state: dict, agent_name: str, default: str = "model") -> str:
    mode = state.get("agent_modes", {}).get(agent_name, default)
    return mode if mode in {"tool", "model", "hybrid"} else default


def agent_uses_model(state: dict, agent_name: str, default: str = "model") -> bool:
    return agent_mode(state, agent_name, default) in {"model", "hybrid"}


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def call_agent_json(
    *,
    agent_name: str,
    state: dict,
    system_prompt: str,
    payload: dict,
    fallback: dict,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> dict:
    if wants_mock():
        return fallback

    model = state.get("agent_models", {}).get(agent_name) or state.get("model")
    user_prompt = (
        "请严格基于以下状态生成结果。只输出一个合法 JSON 对象，不要输出 Markdown。\n\n"
        f"{compact_json(payload)}"
    )
    try:
        result = bailian_chat_client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except BailianResponseError as exc:
        warning = f"{agent_name} 调用百炼模型失败，已使用本地兜底结果：{exc}"
        state.setdefault("llm_warnings", []).append(warning)
        fallback["_llm_warning"] = warning
        return fallback

    if not isinstance(result, dict):
        warning = f"{agent_name} 返回结果不是 JSON object，已使用本地兜底结果。"
        state.setdefault("llm_warnings", []).append(warning)
        fallback["_llm_warning"] = warning
        return fallback
    return result


def ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    return []


def ensure_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
