from typing import Literal


BailianModelName = Literal[
    "qwen3.6-plus-2026-04-02",
    "glm-5.1",
    "qwen3.6-flash-2026-04-16",
    "qwen3.6-35b-a3b",
    "deepseek-v4-flash",
    "qwen3.6-flash",
]


BAILIAN_MODEL_PRESETS: dict[str, dict[str, str]] = {
    "qwen3.6-plus-2026-04-02": {
        "label": "Qwen 3.6 Plus",
        "use_case": "主线规划、项目圣经、终稿生成",
    },
    "glm-5.1": {
        "label": "GLM 5.1",
        "use_case": "备选推理与文本风格对照",
    },
    "qwen3.6-flash-2026-04-16": {
        "label": "Qwen 3.6 Flash 2026-04-16",
        "use_case": "快速改写、批量质检",
    },
    "qwen3.6-35b-a3b": {
        "label": "Qwen 3.6 35B A3B",
        "use_case": "成本可控的主笔编剧",
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "use_case": "结构化审查、节奏问题定位",
    },
    "qwen3.6-flash": {
        "label": "Qwen 3.6 Flash",
        "use_case": "低延迟交互和局部润色",
    },
}


DEFAULT_BAILIAN_MODEL: BailianModelName = "qwen3.6-flash"
