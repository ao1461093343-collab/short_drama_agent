from app.graph.nodes.common import append_trace
from app.graph.nodes.llm_helpers import agent_uses_model, call_agent_json, ensure_dict, ensure_list
from app.graph.state import ScriptState
from app.memory.manager import memory_manager


def lead_writer_node(state: ScriptState) -> ScriptState:
    bible = ensure_dict(state.get("project_bible"))
    memory_context = memory_manager.build_context_packet(state)
    episode_number = state.get("episode_number", 1)
    open_threads = memory_context.get("open_threads", [])
    previous_hook = open_threads[-1] if open_threads else "女主被当众要求向冒名者敬酒。"
    severe_feedback = [
        item["message"]
        for item in ensure_list(state.get("review_findings"))
        if isinstance(item, dict) and item.get("severity") == "SEVERE"
    ]
    mcp_context = ensure_dict(state.get("mcp_context"))
    previous_titles = [
        str(item.get("title"))
        for item in ensure_list(state.get("previous_episodes"))
        if isinstance(item, dict) and item.get("title")
    ]

    fallback_outline = {
        "episode": episode_number,
        "title": f"第{episode_number}集：她把谎言逼到台前",
        "beats": [
            f"前三秒：承接上集悬念——{previous_hook}",
            "冲突升级：对立面暗示女主身份低微。",
            "信息翻转：女主拿出一份只有核心成员才知道的证据。",
            "结尾钩子：男主认出女主真正身份，却选择暂时沉默。",
        ],
    }

    fallback_script = {
        "agent": "主笔编剧",
        "episode": episode_number,
        "title": fallback_outline["title"],
        "hook_3s": f"许曼冷笑：\"上次让你逃了，这次你还拿什么翻盘？\"",
        "scenes": [
            {
                "scene_no": 1,
                "location": "酒店宴会厅",
                "duration_sec": 35,
                "action": "镜头推近，林夏站在人群中央，手里的酒杯没有动。",
                "dialogue": [
                    {"speaker": "许曼", "line": "敬酒啊，别让大家等你一个人。"},
                    {"speaker": "林夏", "line": "这杯酒，我敬不起。"},
                    {"speaker": "许曼", "line": "装什么清高？你站在这里，都是林家给你的脸。"},
                    {"speaker": "林夏", "line": "脸是自己挣的，不是靠抢别人的名字贴上去。"},
                    {"speaker": "宾客甲", "line": "她这话什么意思？难道许曼身份有问题？"},
                ],
            },
            {
                "scene_no": 2,
                "location": "宴会厅主桌",
                "duration_sec": 45,
                "action": "周砚抬眼，发现林夏手上的旧戒痕。",
                "dialogue": [
                    {"speaker": "周砚", "line": "你手上的痕迹，是林家的传承戒？"},
                    {"speaker": "许曼", "line": "她偷戴的吧，别被她骗了。"},
                    {"speaker": "林夏", "line": "是不是偷的，问问这份股权托管书就知道。"},
                    {"speaker": "周砚", "line": "这编号……只有董事会密档里才有。"},
                    {"speaker": "许曼", "line": "假的！她连林家的门都进不去，怎么可能有密档？"},
                    {"speaker": "林夏", "line": "我进不去门，是因为有人把门锁从里面换了。"},
                ],
            },
            {
                "scene_no": 3,
                "location": "宴会厅入口",
                "duration_sec": 40,
                "action": "大屏幕亮起，托管书编号与林夏姓名同时出现。",
                "dialogue": [
                    {"speaker": "林夏", "line": "今天不是我来攀你们，是你们终于等到我。"},
                    {"speaker": "周砚", "line": "原来你才是林家真正的继承人。"},
                    {"speaker": "许曼", "line": "周砚，你别听她的！她是在拖时间。"},
                    {"speaker": "林夏", "line": "对，我就在拖。拖到审计组进门。"},
                    {"speaker": "保镖", "line": "林小姐，董事会的人到了。"},
                ],
            },
        ],
        "ending_hook": "许曼手机震动，屏幕弹出：\"她回来了，计划提前。\"",
        "rewritten_from_feedback": severe_feedback,
        "bible_logline": bible.get("logline"),
    }

    if agent_uses_model(state, "主笔编剧", default="model"):
        result = call_agent_json(
            agent_name="主笔编剧",
            state=state,
            system_prompt=(
                f"你是短剧主笔编剧。根据项目圣经生成第 {episode_number} 集短视频剧本。"
                "如果 episode_number 大于 1，必须承接 previous_episodes、open_threads 和 memory_context，不能从第一集重新开始。"
                "本集标题必须体现本集新冲突，不要照搬历史集名。必须内建前三秒钩子，"
                "台词短、冲突强、适合竖屏拍摄。若收到 SEVERE 审查意见，必须重写节奏断裂处。"
                "本集内容必须扎实：建议 3-4 个场景，总台词不少于 12 句，理想为 14-18 句；"
                "每个主要场景至少 3-5 句连续对话。场景代表同一时间地点的一段连续戏，"
                "不要一句台词就切一个新场景；同一场对峙、逼问、反击必须留在同一场景内推进。"
                "每场包含动作推进、情绪反应、信息翻转，不要只有台词清单。"
                "只输出 JSON，字段必须包含 episode_outline 和 draft_script。draft_script 必须包含 "
                "agent, episode, title, hook_3s, scenes, ending_hook。scenes 中每项包含 scene_no, "
                "location, duration_sec, action, dialogue。dialogue 中每项包含 speaker, line。"
            ),
            payload={
                "project_bible": bible,
                "planning_report": state.get("planning_report"),
                "mcp_context": {
                    "templates": ensure_list(mcp_context.get("templates"))[:1],
                    "platform_rules": ensure_list(mcp_context.get("platform_rules"))[:1],
                },
                "memory_context": memory_context,
                "episode_number": episode_number,
                "episode_count": state.get("episode_count"),
                "target_duration_sec": state.get("target_duration_sec"),
                "severe_feedback": severe_feedback,
                "previous_episode_titles": previous_titles,
            },
            fallback={"episode_outline": fallback_outline, "draft_script": fallback_script},
            temperature=0.65,
            max_tokens=4000,
        )
    else:
        result = {"episode_outline": fallback_outline, "draft_script": fallback_script}

    result = ensure_dict(result)
    episode_outline = ensure_dict(result.get("episode_outline")) or fallback_outline
    draft_script = ensure_dict(result.get("draft_script")) or fallback_script
    episode_outline = _normalize_outline(episode_outline, fallback_outline, episode_number)
    draft_script = _normalize_script(draft_script, fallback_script, episode_number)
    draft_script["title"] = _dedupe_episode_title(
        str(draft_script.get("title") or fallback_script["title"]),
        episode_number,
        previous_titles,
    )

    return {
        **state,
        "stage": "writing",
        "episode_outline": episode_outline,
        "draft_script": draft_script,
        "memory_context": memory_context,
        "trace": append_trace(state, "主笔编剧", "完成单集初稿，并强化前三秒钩子。"),
    }


def _dedupe_episode_title(title: str, episode_number: int, previous_titles: list[str]) -> str:
    clean = title.strip() or f"第{episode_number}集"
    if clean not in previous_titles:
        return clean
    return f"第{episode_number}集：新的反转逼近"


def _normalize_outline(outline: dict, fallback: dict, episode_number: int) -> dict:
    normalized = dict(outline) if isinstance(outline, dict) else dict(fallback)
    normalized["episode"] = episode_number
    if not isinstance(normalized.get("beats"), list):
        normalized["beats"] = fallback.get("beats", [])
    normalized["title"] = str(normalized.get("title") or fallback.get("title") or f"第{episode_number}集")
    return normalized


def _normalize_script(script: dict, fallback: dict, episode_number: int) -> dict:
    normalized = dict(script) if isinstance(script, dict) else dict(fallback)
    normalized["agent"] = str(normalized.get("agent") or fallback.get("agent") or "主笔编剧")
    normalized["episode"] = episode_number
    normalized["title"] = str(normalized.get("title") or fallback.get("title") or f"第{episode_number}集")
    normalized["hook_3s"] = str(normalized.get("hook_3s") or fallback.get("hook_3s") or "")
    normalized["ending_hook"] = str(normalized.get("ending_hook") or fallback.get("ending_hook") or "")

    scenes = normalized.get("scenes")
    if not isinstance(scenes, list):
        scenes = fallback.get("scenes", [])
    normalized_scenes = [
        _normalize_scene(scene, index + 1)
        for index, scene in enumerate(scenes)
        if isinstance(scene, dict)
    ]
    if not normalized_scenes:
        normalized_scenes = fallback.get("scenes", [])
    normalized["scenes"] = normalized_scenes
    return normalized


def _normalize_scene(scene: dict, scene_no: int) -> dict:
    dialogue = scene.get("dialogue")
    if not isinstance(dialogue, list):
        dialogue = []
    return {
        "scene_no": _safe_int(scene.get("scene_no"), scene_no),
        "location": str(scene.get("location") or "待定场景"),
        "duration_sec": _safe_int(scene.get("duration_sec"), 30),
        "action": str(scene.get("action") or ""),
        "dialogue": [
            {
                "speaker": str(line.get("speaker") or ""),
                "line": str(line.get("line") or ""),
            }
            for line in dialogue
            if isinstance(line, dict)
        ],
    }


def _safe_int(value, fallback: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else fallback
