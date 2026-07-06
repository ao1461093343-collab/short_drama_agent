import json
import re
from typing import Any

from openai import APITimeoutError, OpenAI

from app.core.config import settings


class BailianResponseError(RuntimeError):
    pass


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise BailianResponseError("Model response did not contain a JSON object.")


def _compact_invalid_json(text: str, limit: int = 6000) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    half = limit // 2
    return f"{clean[:half]}\n...\n{clean[-half:]}"


class BailianChatClient:
    """OpenAI-compatible client for Alibaba Bailian / DashScope Qwen models."""

    def __init__(self) -> None:
        if not settings.dashscope_api_key and not settings.use_mock_llm:
            raise RuntimeError("DASHSCOPE_API_KEY is required when USE_MOCK_LLM=false")

        self.client = OpenAI(
            api_key=settings.dashscope_api_key or "mock-key",
            base_url=settings.dashscope_base_url,
            timeout=settings.bailian_timeout_seconds,
            max_retries=0,
        )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if settings.use_mock_llm:
            return {
                "mock": True,
                "model": model or settings.bailian_model,
                "content": user_prompt[:120],
                "tool_count": len(tools or []),
            }

        try:
            completion = self.client.chat.completions.create(
                model=model or settings.bailian_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens or settings.bailian_max_tokens,
                response_format={"type": "json_object"},
            )
        except APITimeoutError as exc:
            raise BailianResponseError(
                f"百炼模型请求超时，当前超时为 {settings.bailian_timeout_seconds} 秒。"
                "可以换用 qwen3.6-flash，或继续调高 BAILIAN_TIMEOUT_SECONDS。"
            ) from exc
        message = completion.choices[0].message
        if message.tool_calls:
            return {"tool_calls": [call.model_dump() for call in message.tool_calls]}
        raw_content = message.content or "{}"
        try:
            return _extract_json_object(raw_content)
        except (json.JSONDecodeError, BailianResponseError) as exc:
            try:
                return self._repair_json(raw_content, model or settings.bailian_model, max_tokens)
            except (json.JSONDecodeError, BailianResponseError) as repair_exc:
                raise BailianResponseError(
                    f"Failed to parse model JSON: {exc}; repair failed: {repair_exc}"
                ) from repair_exc

    def _repair_json(self, raw_content: str, model: str, max_tokens: int | None = None) -> dict[str, Any]:
        repair_prompt = (
            "下面是一段模型输出的无效 JSON。请只修复 JSON 语法错误，不要新增解释，"
            "不要改变字段含义，不要输出 Markdown，只输出一个合法 JSON 对象。\n\n"
            f"{_compact_invalid_json(raw_content)}"
        )
        completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是严格的 JSON 修复器，只输出合法 JSON 对象。"},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0,
            max_tokens=max(max_tokens or settings.bailian_max_tokens, 4000),
            response_format={"type": "json_object"},
        )
        fixed_content = completion.choices[0].message.content or "{}"
        return _extract_json_object(fixed_content)


bailian_chat_client = BailianChatClient()
