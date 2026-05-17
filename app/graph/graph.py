"""
LangGraph StateGraph definition for the SRS generator workflow.

Topology:
Phase 1 (Ingestion) → Phase 2 (Elicitation with 4 Q&A groups) → 
Phase 3 (Parallel drafting) → Phase 4 (Diagrams) → Phase 5 (Finalization) → END

Interrupts at:
- After each elicitation group (wait for user response)
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.nodes import (
    ingest_and_map_domain,
    generate_elicitation_plan,
    generate_single_elicitation_question,
    classify_and_store_answers,
    draft_from_approved_outline,
    revise_selected_section,
    generate_mermaid_diagrams,
    finalize_and_export,
)
from app.graph.state import SRSState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Conditional Routing Functions
# ─────────────────────────────────────────────────────────────────────────────


def _route_after_single_question(
    state: SRSState,
) -> Literal["classify_and_store_answers"]:
    """After user answers a question, store it."""
    return "classify_and_store_answers"


def _route_from_start(state: SRSState) -> Literal["ingest_and_map_domain", "revise_selected_section"]:
    """Route to ingestion (full run) or direct to section revision."""
    if state.get("revision_mode", False):
        return "revise_selected_section"
    return "ingest_and_map_domain"


def _route_after_storing_answer(
    state: SRSState,
) -> Literal["generate_single_elicitation_question", "generate_elicitation_plan", "draft_from_approved_outline"]:
    """After storing answer, check if more questions in plan, more groups, or done."""
    question_index = state.get("elicitation_question_index", 0)
    question_plan = state.get("elicitation_question_plan", [])
    group_index = state.get("pending_group_index", 0)

    # More questions in current plan
    if question_index < len(question_plan):
        return "generate_single_elicitation_question"

    # Check if we need to move to next group
    elif group_index < 3:
        return "generate_elicitation_plan"  # Will handle group increment

    # All groups and questions done → go straight to drafting
    else:
        return "draft_from_approved_outline"


# ─────────────────────────────────────────────────────────────────────────────
# Build StateGraph
# ─────────────────────────────────────────────────────────────────────────────


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    """
    Build the LangGraph StateGraph.

    Topology (Elicitation Phase - One Question at a Time):
    START
      → ingest_and_map_domain
      → generate_elicitation_plan (lightweight: creates topic list)
      → generate_single_elicitation_question (ask one Q)
      → classify_and_store_answers (store answer)
      ├─ [if more questions in plan] → generate_single_elicitation_question (loop)
      ├─ [if more groups] → generate_elicitation_plan (next group)
      └─ [if all done] → draft_from_approved_outline
        → generate_mermaid_diagrams
        → finalize_and_export
          → END
    """
    graph = StateGraph(SRSState)

    # ────────────────────────────────────────────────────────────────────────
    # Add nodes
    # ────────────────────────────────────────────────────────────────────────

    graph.add_node("ingest_and_map_domain", ingest_and_map_domain)
    graph.add_node("revise_selected_section", revise_selected_section)
    graph.add_node("generate_elicitation_plan", generate_elicitation_plan)
    graph.add_node("generate_single_elicitation_question", generate_single_elicitation_question)
    graph.add_node("classify_and_store_answers", classify_and_store_answers)
    graph.add_node("draft_from_approved_outline", draft_from_approved_outline)
    graph.add_node("generate_mermaid_diagrams", generate_mermaid_diagrams)
    graph.add_node("finalize_and_export", finalize_and_export)

    # ────────────────────────────────────────────────────────────────────────
    # Add edges
    # ────────────────────────────────────────────────────────────────────────

    # START → [conditional: revision or ingestion]
    graph.add_conditional_edges(
        START,
        _route_from_start,
        {
            "ingest_and_map_domain": "ingest_and_map_domain",
            "revise_selected_section": "revise_selected_section",
        },
    )

    # ingest_and_map_domain → generate_elicitation_plan
    graph.add_edge("ingest_and_map_domain", "generate_elicitation_plan")

    # generate_elicitation_plan → generate_single_elicitation_question
    graph.add_edge("generate_elicitation_plan", "generate_single_elicitation_question")

    # generate_single_elicitation_question → classify_and_store_answers
    graph.add_conditional_edges(
        "generate_single_elicitation_question",
        _route_after_single_question,
        {"classify_and_store_answers": "classify_and_store_answers"},
    )

    # classify_and_store_answers → [conditional: next question, next group, or drafting]
    graph.add_conditional_edges(
        "classify_and_store_answers",
        _route_after_storing_answer,
        {
            "generate_single_elicitation_question": "generate_single_elicitation_question",
            "generate_elicitation_plan": "generate_elicitation_plan",
            "draft_from_approved_outline": "draft_from_approved_outline",
        },
    )

    # revise_selected_section → finalize_and_export
    graph.add_edge("revise_selected_section", "finalize_and_export")

    # draft_from_approved_outline → generate_mermaid_diagrams
    graph.add_edge("draft_from_approved_outline", "generate_mermaid_diagrams")

    # generate_mermaid_diagrams → finalize_and_export
    graph.add_edge("generate_mermaid_diagrams", "finalize_and_export")

    # finalize_and_export → END
    graph.add_edge("finalize_and_export", END)

    # ────────────────────────────────────────────────────────────────────────
    # Compile with checkpoint saver if provided
    # ────────────────────────────────────────────────────────────────────────

    if checkpointer:
        compiled_graph = graph.compile(checkpointer=checkpointer)
    else:
        compiled_graph = graph.compile()

    logger.info("SRS generator graph compiled successfully")

    return compiled_graph
