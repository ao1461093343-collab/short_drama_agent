from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.graph.nodes.orchestrator import orchestrator_node
from app.graph.nodes.quality_reviewer import quality_reviewer_node
from app.graph.nodes.revision_editor import revision_editor_node
from app.graph.nodes.shot_director import shot_director_node
from app.graph.nodes.world_builder import world_builder_node
from app.graph.nodes.lead_writer import lead_writer_node
from app.graph.routing import route_after_review, route_after_revision
from app.graph.state import ScriptState


def build_script_graph(checkpointer=None, interrupt_after=None):
    graph = StateGraph(ScriptState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("world_builder", world_builder_node)
    graph.add_node("lead_writer", lead_writer_node)
    graph.add_node("quality_review", quality_reviewer_node)
    graph.add_node("revision", revision_editor_node)
    graph.add_node("shot_director", shot_director_node)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "world_builder")
    graph.add_edge("world_builder", "lead_writer")
    graph.add_edge("lead_writer", "quality_review")
    graph.add_conditional_edges(
        "quality_review",
        route_after_review,
        {
            "world_builder": "world_builder",
            "lead_writer": "lead_writer",
            "revision": "revision",
            "shot_director": "shot_director",
            "blocked": END,
        },
    )
    graph.add_conditional_edges(
        "revision",
        route_after_revision,
        {
            "quality_review": "quality_review",
            "shot_director": "shot_director",
        },
    )
    graph.add_edge("shot_director", END)

    return graph.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)


script_graph = build_script_graph()
interactive_script_graph = build_script_graph(
    checkpointer=MemorySaver(),
    interrupt_after=["lead_writer"],
)
