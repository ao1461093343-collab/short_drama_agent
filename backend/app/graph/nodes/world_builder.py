from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_uses_model, call_agent_json, ensure_dict, ensure_list
from app.graph.state import ScriptState
from app.memory.manager import memory_manager


def world_builder_node(state: ScriptState) -> ScriptState:
    brief = state["user_brief"]
    planning = ensure_dict(state.get("planning_report"))
    memory_context = memory_manager.build_context_packet(state)
    fatal_feedback = [
        item["message"]
        for item in ensure_list(state.get("review_findings"))
        if isinstance(item, dict) and item.get("severity") == "FATAL"
    ]
    mcp_context = ensure_dict(state.get("mcp_context"))
    existing_bible = ensure_dict(state.get("project_bible"))
    if existing_bible and not fatal_feedback:
        return {
            **state,
            "stage": "world_building",
            "project_bible": existing_bible,
            "memory_context": memory_manager.build_context_packet({**state, "project_bible": existing_bible}),
            "trace": append_trace(state, "世界观构建", "复用已有项目圣经，保持长篇设定连续。"),
        }

    fallback = {
        "agent": "世界观构建",
        "logline": f"围绕「{brief}」展开的高反转短剧故事。",
        "theme": "欲望、身份误判与情感补偿",
        "main_line": {
            "start": "主角被迫卷入一个看似无解的关系困局。",
            "middle": "主角逐步识破利益局，同时暴露隐藏身份或能力。",
            "end": "主角完成反制，并留下更大的系列悬念。",
        },
        "characters": [
            {
                "name": "林夏",
                "role": "主角",
                "profile": "外表柔弱，实际极擅长观察和布局。",
                "desire": "证明自己不是可被随意牺牲的人。",
            },
            {
                "name": "周砚",
                "role": "关键盟友",
                "profile": "冷静克制，掌握一部分真相。",
                "desire": "用理性弥补过去的亏欠。",
            },
            {
                "name": "许曼",
                "role": "对立面",
                "profile": "擅长操纵舆论，害怕失去既得利益。",
                "desire": "维持精心包装的人设。",
            },
        ],
        "rules": [
            "角色动机必须服务主线冲突",
            "每集结尾留下可拍摄的强动作或强台词钩子",
            "人物关系变化必须能在前文找到伏笔",
        ],
        "platform_fit": planning.get("platform_notes", []),
        "rebuilt_from_feedback": fatal_feedback,
    }

    if agent_uses_model(state, "世界观构建", default="model"):
        bible = call_agent_json(
            agent_name="世界观构建",
            state=state,
            system_prompt=(
                "你是短剧项目的世界观构建 Agent。你要输出项目圣经，包含主线、人设、人物欲望、"
                "创作规则和平台适配。若收到 FATAL 审查意见，必须修复吃书问题。"
                "只输出 JSON，字段必须包含 agent, logline, theme, main_line, characters, rules, "
                "platform_fit, rebuilt_from_feedback。"
            ),
            payload={
                "user_brief": brief,
                "planning_report": planning,
                "mcp_context": {
                    "platform_rules": ensure_list(mcp_context.get("platform_rules"))[:1],
                    "example_cases": ensure_list(mcp_context.get("example_cases"))[:1],
                },
                "memory_context": memory_context,
                "fatal_feedback": fatal_feedback,
            },
            fallback=fallback,
            temperature=0.75,
            max_tokens=2200,
        )
    else:
        bible = fallback
    bible = ensure_dict(bible) or fallback

    return {
        **state,
        "stage": "world_building",
        "project_bible": bible,
        "memory_context": memory_manager.build_context_packet({**state, "project_bible": bible}),
        "trace": append_trace(state, "世界观构建", "生成包含主线、人设与创作规则的项目圣经。"),
    }
