"""
LangGraph StateGraph definition for the 5-phase SRS generator workflow.

Topology:
Phase 1 (Ingestion) → Phase 2 (Elicitation with 4 Q&A groups) → 
Phase 3 (Outline approval) → Phase 4 (Parallel drafting) → 
Phase 5 (Review & feedback loop) → Finalization → END

Interrupts at:
- After ingestion (implicit, user sees summary)
- After each elicitation group (wait for user response)
- After outline generation (user approval)
- After draft completion (user feedback)
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
    generate_outline,
    wait_for_outline_approval,
    draft_from_approved_outline,
    present_draft_for_review,
    process_review_feedback,
    finalize_and_export,
)
from app.graph.state import SRSState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Conditional Routing Functions
# ─────────────────────────────────────────────────────────────────────────────


def _route_after_ingestion(state: SRSState) -> Literal["generate_elicitation_plan"]:
    """After ingestion, always proceed to elicitation plan."""
    return "generate_elicitation_plan"


def _route_after_plan(state: SRSState) -> Literal["generate_single_elicitation_question"]:
    """After plan generation, start asking questions."""
    return "generate_single_elicitation_question"


def _route_after_single_question(
    state: SRSState,
) -> Literal["classify_and_store_answers", "generate_single_elicitation_question"]:
    """After user answers a question, store it and check if more questions in plan."""
    question_index = state.get("elicitation_question_index", 0)
    question_plan = state.get("elicitation_question_plan", [])
    
    # Always store the answer first
    return "classify_and_store_answers"


def _route_after_storing_answer(
    state: SRSState,
) -> Literal["generate_single_elicitation_question", "generate_elicitation_plan", "generate_outline"]:
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
    
    # All groups and questions done
    else:
        return "generate_outline"


def _route_after_outline_approval(
    state: SRSState,
) -> Literal["wait_for_outline_approval", "draft_from_approved_outline"]:
    """After outline review, check if approved."""
    if state.get("outline_approved", False):
        return "draft_from_approved_outline"
    else:
        return "wait_for_outline_approval"


def _route_after_draft_feedback(
    state: SRSState,
) -> Literal["process_review_feedback", "finalize_and_export"]:
    """After draft feedback, decide whether to finalize or process more changes."""
    revision_targets = state.get("revision_targets", [])
    if revision_targets:
        return "process_review_feedback"
    else:
        return "finalize_and_export"


# ─────────────────────────────────────────────────────────────────────────────
# Build StateGraph
# ─────────────────────────────────────────────────────────────────────────────


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    """
    Build the 5-phase LangGraph StateGraph.

    Topology (Elicitation Phase - One Question at a Time):
    START
      → ingest_and_map_domain
      → generate_elicitation_plan (lightweight: creates topic list)
      → generate_single_elicitation_question (ask one Q)
      → classify_and_store_answers (store answer)
      ├─ [if more questions in plan] → generate_single_elicitation_question (loop)
      ├─ [if more groups] → generate_elicitation_plan (next group)
      └─ [if all done] → generate_outline
        → wait_for_outline_approval
        ├─ [if not approved] → wait_for_outline_approval (re-wait)
        └─ [if approved] → draft_from_approved_outline
          → present_draft_for_review
          → process_review_feedback
          ├─ [if more edits] → process_review_feedback (loop)
          └─ [if finalize] → finalize_and_export
            → END
    """
    graph = StateGraph(SRSState)

    # ────────────────────────────────────────────────────────────────────────
    # Add nodes
    # ────────────────────────────────────────────────────────────────────────

    graph.add_node("ingest_and_map_domain", ingest_and_map_domain)
    graph.add_node("generate_elicitation_plan", generate_elicitation_plan)
    graph.add_node("generate_single_elicitation_question", generate_single_elicitation_question)
    graph.add_node("classify_and_store_answers", classify_and_store_answers)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("wait_for_outline_approval", wait_for_outline_approval)
    graph.add_node("draft_from_approved_outline", draft_from_approved_outline)
    graph.add_node("present_draft_for_review", present_draft_for_review)
    graph.add_node("process_review_feedback", process_review_feedback)
    graph.add_node("finalize_and_export", finalize_and_export)

    # ────────────────────────────────────────────────────────────────────────
    # Add edges
    # ────────────────────────────────────────────────────────────────────────

    # START → ingest_and_map_domain
    graph.add_edge(START, "ingest_and_map_domain")

    # ingest_and_map_domain → generate_elicitation_plan
    graph.add_conditional_edges(
        "ingest_and_map_domain",
        _route_after_ingestion,
        {"generate_elicitation_plan": "generate_elicitation_plan"},
    )

    # generate_elicitation_plan → generate_single_elicitation_question
    graph.add_conditional_edges(
        "generate_elicitation_plan",
        _route_after_plan,
        {"generate_single_elicitation_question": "generate_single_elicitation_question"},
    )

    # generate_single_elicitation_question → classify_and_store_answers
    graph.add_conditional_edges(
        "generate_single_elicitation_question",
        _route_after_single_question,
        {"classify_and_store_answers": "classify_and_store_answers"},
    )

    # classify_and_store_answers → [conditional: next question, next group, or outline]
    graph.add_conditional_edges(
        "classify_and_store_answers",
        _route_after_storing_answer,
        {
            "generate_single_elicitation_question": "generate_single_elicitation_question",
            "generate_elicitation_plan": "generate_elicitation_plan",
            "generate_outline": "generate_outline",
        },
    )

    # generate_outline → wait_for_outline_approval
    graph.add_edge("generate_outline", "wait_for_outline_approval")

    # wait_for_outline_approval → [conditional: approved or re-wait]
    graph.add_conditional_edges(
        "wait_for_outline_approval",
        _route_after_outline_approval,
        {
            "wait_for_outline_approval": "wait_for_outline_approval",
            "draft_from_approved_outline": "draft_from_approved_outline",
        },
    )

    # draft_from_approved_outline → present_draft_for_review
    graph.add_edge("draft_from_approved_outline", "present_draft_for_review")

    # present_draft_for_review → process_review_feedback
    graph.add_edge("present_draft_for_review", "process_review_feedback")

    # process_review_feedback → [conditional: finalize or loop]
    graph.add_conditional_edges(
        "process_review_feedback",
        _route_after_draft_feedback,
        {
            "process_review_feedback": "process_review_feedback",
            "finalize_and_export": "finalize_and_export",
        },
    )

    # finalize_and_export → END
    graph.add_edge("finalize_and_export", END)

    # ────────────────────────────────────────────────────────────────────────
    # Compile with checkpoint saver if provided
    # ────────────────────────────────────────────────────────────────────────

    if checkpointer:
        compiled_graph = graph.compile(checkpointer=checkpointer)
    else:
        compiled_graph = graph.compile()

    logger.info("5-phase SRS generator graph compiled successfully")

    return compiled_graph
