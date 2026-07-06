from app.graph.state import AgentTrace, ScriptState


def append_trace(state: ScriptState, agent: str, summary: str) -> list[AgentTrace]:
    return [*state.get("trace", []), {"agent": agent, "summary": summary}]
