SCRIPT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "scan_sensitive_terms",
            "description": "Scan script text for platform-sensitive or weak commercial-risk terms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_script_runtime",
            "description": "Calculate total script duration from scene duration fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenes": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["scenes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_script_density",
            "description": "Check dialogue density and fragmented scene switching in a script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenes": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["scenes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_review_findings",
            "description": "Return the highest review severity for routing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["findings"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_dialogue_line",
            "description": "Replace a local dialogue line during minor revision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene_no": {"type": "integer"},
                    "speaker": {"type": "string"},
                    "old_line": {"type": "string"},
                    "new_line": {"type": "string"},
                },
                "required": ["scene_no", "speaker", "old_line", "new_line"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sanitize_sensitive_terms",
            "description": "Deterministically weaken configured sensitive expressions in a script object or text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_shot_table",
            "description": "Convert approved scenes into a tabular shooting script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenes": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["scenes"],
                "additionalProperties": False,
            },
        },
    },
]
