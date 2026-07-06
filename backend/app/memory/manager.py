from app.graph.state import ScriptState
from app.graph.nodes.llm_helpers import ensure_dict, ensure_list
from app.projects.repository import project_repository


class MemoryManager:
    """Builds compact context packets for long multi-episode generation."""

    def build_context_packet(self, state: ScriptState) -> dict:
        bible = ensure_dict(state.get("project_bible"))
        previous_episodes = ensure_list(state.get("previous_episodes"))
        review_findings = [
            item for item in ensure_list(state.get("review_findings")) if isinstance(item, dict)
        ]

        return {
            "series_memory": self._series_memory(bible),
            "character_memory": self._character_memory(bible),
            "episode_memory": self._episode_memory(previous_episodes),
            "open_threads": self._open_threads(previous_episodes),
            "vector_memory": self._vector_memory(state, bible, previous_episodes),
            "latest_review_findings": review_findings[-6:],
        }

    @staticmethod
    def _series_memory(bible: dict) -> dict:
        bible = ensure_dict(bible)
        return {
            "logline": bible.get("logline"),
            "theme": bible.get("theme"),
            "main_line": bible.get("main_line", {}),
            "rules": bible.get("rules", []),
        }

    @staticmethod
    def _character_memory(bible: dict) -> list[dict]:
        bible = ensure_dict(bible)
        characters = ensure_list(bible.get("characters"))
        compact = []
        for character in characters:
            if not isinstance(character, dict):
                continue
            compact.append(
                {
                    "name": character.get("name"),
                    "role": character.get("role"),
                    "desire": character.get("desire"),
                    "current_state": character.get("current_state", "未变化"),
                }
            )
        return compact

    @staticmethod
    def _episode_memory(previous_episodes: list[dict]) -> list[dict]:
        compact = []
        for episode in ensure_list(previous_episodes)[-5:]:
            if not isinstance(episode, dict):
                compact.append(
                    {
                        "episode": None,
                        "title": "",
                        "summary": str(episode),
                        "status_change": [],
                    }
                )
                continue
            compact.append(
                {
                    "episode": episode.get("episode"),
                    "title": episode.get("title"),
                    "summary": episode.get("summary") or episode.get("ending_hook"),
                    "status_change": ensure_list(episode.get("status_change")),
                }
            )
        return compact

    @staticmethod
    def _open_threads(previous_episodes: list[dict]) -> list[str]:
        threads: list[str] = []
        for episode in ensure_list(previous_episodes)[-5:]:
            if not isinstance(episode, dict):
                continue
            hook = episode.get("ending_hook")
            if hook:
                threads.append(hook)
        return threads[-8:]

    @staticmethod
    def _vector_memory(state: ScriptState, bible: dict, previous_episodes: list[dict]) -> list[dict]:
        bible = ensure_dict(bible)
        previous_episodes = ensure_list(previous_episodes)
        query_parts = [
            state.get("user_brief", ""),
            state.get("genre", ""),
            f"episode {state.get('episode_number', '')}",
            bible.get("logline", ""),
            bible.get("theme", ""),
        ]
        if previous_episodes:
            latest = ensure_dict(previous_episodes[-1])
            query_parts.extend(
                [
                    latest.get("summary", ""),
                    latest.get("ending_hook", ""),
                    " ".join(str(item) for item in ensure_list(latest.get("status_change"))),
                ]
            )
        query = " ".join(str(part).strip() for part in query_parts if str(part or "").strip())
        return project_repository.search_memory(state.get("project_id"), query)


memory_manager = MemoryManager()
