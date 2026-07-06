from app.graph.state import ScriptState


def route_after_review(state: ScriptState) -> str:
    status = state.get("review_status", "PASS")
    if (
        status != "PASS"
        and state.get("revision_round", 0) >= state.get("max_revision_rounds", 3)
    ):
        return "blocked"

    if status == "FATAL":
        return "world_builder"
    if status == "SEVERE":
        return "lead_writer"
    if status == "MINOR":
        return "revision"
    return "shot_director"


def route_after_revision(state: ScriptState) -> str:
    return "quality_review"
