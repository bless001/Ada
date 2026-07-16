from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.workflow.nodes import make_nodes
from planning_agent_core.workflow.routing import route_after_ambiguity
from planning_agent_core.workflow.state import PlanningGraphState


def build_planning_graph(db: AsyncSession):
    nodes = make_nodes(db)

    graph = StateGraph(PlanningGraphState)

    graph.add_node("load_session", nodes["load_session"])
    graph.add_node("load_document_context", nodes["load_document_context"])
    graph.add_node("assess_ambiguity", nodes["assess_ambiguity"])
    graph.add_node("save_clarification_questions", nodes["save_clarification_questions"])
    graph.add_node("draft_plan", nodes["draft_plan"])
    graph.add_node("persist_plan", nodes["persist_plan"])
    graph.add_node("build_context_capsules", nodes["build_context_capsules"])
    graph.add_node("enqueue_provisioning", nodes["enqueue_provisioning"])

    graph.add_edge(START, "load_session")
    graph.add_edge("load_session", "load_document_context")
    graph.add_edge("load_document_context", "assess_ambiguity")

    graph.add_conditional_edges(
        "assess_ambiguity",
        route_after_ambiguity,
        {
            "needs_clarification": "save_clarification_questions",
            "ready_for_planning": "draft_plan",
        },
    )

    graph.add_edge("save_clarification_questions", END)

    graph.add_edge("draft_plan", "persist_plan")
    graph.add_edge("persist_plan", "build_context_capsules")
    graph.add_edge("build_context_capsules", "enqueue_provisioning")
    graph.add_edge("enqueue_provisioning", END)

    return graph.compile()