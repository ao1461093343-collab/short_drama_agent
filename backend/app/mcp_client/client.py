from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ScriptMcpClient:
    """Context adapter for MCP servers and local fallback resources."""

    async def list_available_contexts(self) -> list[str]:
        return ["script_templates", "platform_rules", "example_cases"]

    async def search_script_cases(self, query: str) -> list[dict]:
        return [
            {
                "title": "身份反转开场模板",
                "score": 0.82,
                "snippet": f"与「{query}」相近的开场：误认、压迫、证据反杀。",
            }
        ]

    def get_context_bundle(self, query: str, platform: str) -> dict:
        return {
            "templates": self._read_markdown_dir(PROJECT_ROOT / "data" / "templates"),
            "platform_rules": self._read_markdown_dir(PROJECT_ROOT / "data" / "platform_rules"),
            "example_cases": [
                {
                    "title": "身份反转开场模板",
                    "snippet": f"与「{query}」相近：误认、压迫、证据反杀。",
                    "platform": platform,
                }
            ],
        }

    @staticmethod
    def _read_markdown_dir(path: Path) -> list[dict]:
        if not path.exists():
            return []
        resources = []
        for item in path.glob("*.md"):
            resources.append({"name": item.stem, "content": item.read_text(encoding="utf-8")})
        return resources


script_mcp_client = ScriptMcpClient()
