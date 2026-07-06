import os

os.environ["USE_MOCK_LLM"] = "true"
os.environ["STORAGE_BACKEND"] = "json"
os.environ["ENABLE_VECTOR_MEMORY"] = "false"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["EMBEDDING_DIMENSION"] = "1024"

from fastapi.testclient import TestClient

from app.api.routes import _next_episode_number
from app.core.config import settings
from app.main import app
from app.projects import repository as repository_module
from app.projects.repository import JsonProjectRepository
from app.storage import db as db_module
from app.graph.nodes.lead_writer import _normalize_script
from app.graph.nodes.quality_reviewer import quality_reviewer_node
from app.graph.nodes.revision_editor import revision_editor_node
from app.exporters.script_exporter import export_script_pdf

settings.use_mock_llm = True
settings.enable_vector_memory = False
settings.embedding_provider = "mock"
settings.embedding_dimension = 1024


client = TestClient(app)


def test_health_models_and_capabilities_endpoints() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    models = client.get("/api/models")
    assert models.status_code == 200
    models_payload = models.json()
    assert models_payload["custom_model_allowed"] is True
    assert "qwen3.6-flash" in {item["name"] for item in models_payload["models"]}

    capabilities = client.get("/api/capabilities")
    assert capabilities.status_code == 200
    capabilities_payload = capabilities.json()
    assert capabilities_payload["workflow"]["events"].startswith("SSE stream")
    assert capabilities_payload["storage"]["backend"] in {"json", "postgres"}


def test_mock_script_generation_smoke() -> None:
    response = client.post(
        "/api/scripts/create",
        json={
            "user_brief": "真千金在订婚宴反击冒名者，下一集要继续身份反转。",
            "model": "qwen3.6-flash",
            "fast_mode": True,
            "target_duration_sec": 180,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "PASS"
    assert payload["final_script"]["scenes"]
    assert payload["shooting_script"]


def test_next_episode_number_uses_max_episode_not_count() -> None:
    previous = [{"episode": 1}, {"episode": "3"}, {"episode": 2}]
    assert _next_episode_number(previous) == 4


def test_json_project_repository_delete_project_and_version(tmp_path, monkeypatch) -> None:
    projects_file = tmp_path / "projects.json"
    monkeypatch.setattr(repository_module, "PROJECTS_FILE", projects_file)

    repository = JsonProjectRepository()
    first = repository.save_version(
        None,
        {
            "episode_number": 1,
            "user_brief": "项目开端",
            "final_script": {"title": "第一集", "episode": 1, "scenes": []},
            "project_bible": {"logline": "连续短剧"},
        },
        "第一集",
    )
    project_id = first["project"]["id"]
    third = repository.save_version(
        project_id,
        {
            "episode_number": 3,
            "user_brief": "项目延续",
            "final_script": {"title": "第三集", "episode": 3, "scenes": []},
            "project_bible": {"logline": "连续短剧"},
        },
        "第三集",
    )

    assert repository.next_episode_number(project_id) == 4
    assert repository.delete_version(project_id, third["version"]["id"]) is True
    assert repository.next_episode_number(project_id) == 2
    assert repository.delete_project(project_id) is True
    assert repository.get_project(project_id) is None


def test_embedding_dimension_migration_rebuilds_vector_column(monkeypatch) -> None:
    executed: list[str] = []

    class FakeScalarResult:
        @staticmethod
        def scalar() -> str:
            return "vector(1536)"

    class FakeConnection:
        def execute(self, statement):
            sql = str(statement)
            executed.append(sql)
            if "format_type" in sql:
                return FakeScalarResult()
            return None

    monkeypatch.setattr(db_module.settings, "embedding_dimension", 1024)
    db_module._ensure_embedding_dimension(FakeConnection())

    joined = "\n".join(executed)
    assert "DROP INDEX IF EXISTS knowledge_chunks_embedding_idx" in joined
    assert "ALTER COLUMN embedding TYPE vector(1024) USING NULL" in joined
    assert "Embedding dimension changed; reindex required." in joined


def test_lead_writer_normalizes_loose_model_script_shape() -> None:
    fallback = {
        "agent": "主笔编剧",
        "episode": 2,
        "title": "第2集",
        "hook_3s": "开场钩子",
        "ending_hook": "结尾钩子",
        "scenes": [
            {
                "scene_no": 1,
                "location": "走廊",
                "duration_sec": 30,
                "action": "对峙",
                "dialogue": [{"speaker": "女主", "line": "开始了。"}],
            }
        ],
    }
    loose = {
        "title": "松散结构",
        "scenes": [
            {
                "scene_no": "03",
                "location": "宴会厅",
                "duration_sec": "35秒",
                "action": "她转身亮出证据。",
                "dialogue": "女主：看清楚。",
            }
        ],
    }

    normalized = _normalize_script(loose, fallback, 2)

    assert normalized["episode"] == 2
    assert normalized["scenes"][0]["scene_no"] == 3
    assert normalized["scenes"][0]["duration_sec"] == 35
    assert normalized["scenes"][0]["dialogue"] == []


def test_minor_sensitive_term_is_sanitized_and_does_not_block_final_script() -> None:
    state = {
        "draft_script": {
            "title": "第1集",
            "scenes": [
                {
                        "scene_no": 1,
                        "location": "走廊",
                        "duration_sec": 20,
                        "action": "对峙",
                        "dialogue": [
                            {"speaker": "反派", "line": "我要弄死你。"},
                            {"speaker": "女主", "line": "你可以试试。"},
                            {"speaker": "反派", "line": "没人会信你。"},
                            {"speaker": "女主", "line": "那就让证据说话。"},
                            {"speaker": "助理", "line": "监控备份已经恢复。"},
                            {"speaker": "反派", "line": "你什么时候做的？"},
                            {"speaker": "女主", "line": "从你第一次撒谎开始。"},
                            {"speaker": "旁观者", "line": "她手里真有证据。"},
                            {"speaker": "反派", "line": "你敢公开？"},
                            {"speaker": "女主", "line": "我等的就是这一刻。"},
                            {"speaker": "助理", "line": "直播已经接入。"},
                            {"speaker": "女主", "line": "现在，该你解释了。"},
                        ],
                    }
                ],
            },
        "review_findings": [
            {
                "severity": "MINOR",
                "category": "平台敏感词",
                "message": "发现“弄死”：暴力表达过强，建议弱化为情绪台词。",
                "target": "draft_script",
            }
        ],
        "revision_round": 2,
        "max_revision_rounds": 3,
        "agent_modes": {"改写迭代": "tool"},
        "fast_mode": True,
        "trace": [],
    }

    revised = revision_editor_node(state)

    assert "弄死" not in str(revised["draft_script"])
    assert "让他付出代价" in str(revised["draft_script"])

    reviewed = quality_reviewer_node(
        {
            **revised,
            "revision_round": 3,
            "max_revision_rounds": 3,
            "agent_modes": {"综合质检": "tool"},
        }
    )

    assert reviewed["review_status"] == "PASS"
    assert reviewed["workflow_error"] == ""
    assert "弄死" not in str(reviewed["final_script"])


def test_pdf_export_handles_long_shot_table_text() -> None:
    long_visual = "镜头缓慢推进，女主抬手翻开档案袋，证据页一张张铺满桌面。" * 12
    long_dialogue = "女主：这不是解释，是清算。反派：你以为这样就能赢吗？" * 10
    result = {
        "project_bible": {"logline": "测试长分镜导出", "theme": "反击与成长"},
        "final_script": {
            "title": "长分镜测试",
            "hook_3s": "她把证据拍在桌上。",
            "scenes": [
                {
                    "scene_no": 1,
                    "location": "会议室",
                    "duration_sec": 45,
                    "action": long_visual,
                    "dialogue": [{"speaker": "女主", "line": "这一次，轮到你解释。"}],
                }
            ],
        },
        "shooting_script": [
            {
                "镜号": f"{index}-1",
                "场景": "会议室",
                "画面": long_visual,
                "台词": long_dialogue,
            }
            for index in range(1, 8)
        ],
    }

    path = export_script_pdf(result)

    assert path.exists()
    assert path.stat().st_size > 2000


def test_quality_review_flags_short_or_fragmented_script() -> None:
    reviewed = quality_reviewer_node(
        {
            "draft_script": {
                "title": "过短剧本",
                "scenes": [
                    {
                        "scene_no": 1,
                        "location": "走廊",
                        "duration_sec": 20,
                        "action": "她看向对方。",
                        "dialogue": [{"speaker": "女主", "line": "你输了。"}],
                    },
                    {
                        "scene_no": 2,
                        "location": "门口",
                        "duration_sec": 20,
                        "action": "他沉默。",
                        "dialogue": [{"speaker": "反派", "line": "不可能。"}],
                    },
                ],
            },
            "revision_round": 0,
            "max_revision_rounds": 3,
            "agent_modes": {"综合质检": "tool"},
            "fast_mode": True,
            "trace": [],
        }
    )

    assert reviewed["review_status"] == "SEVERE"
    messages = " ".join(item["message"] for item in reviewed["review_findings"])
    assert "单集内容偏短" in messages
    assert "一句台词换一次场景" in messages
