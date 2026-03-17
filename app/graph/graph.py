"""
LangGraph StateGraph definition for the SRS generator workflow.

Graph topology:
    START
      → retrieve_rag_context
      → elicit_requirements
      → evaluate_completeness
      ↙ [missing?]          ↘ [complete]
    ask_clarifying_questions   classify_requirements
      ↓ (HITL resume)             ↓ (fan-out via Send)
    evaluate_completeness     ┌───────────────────────────┐
                              │ draft_section_3_fr         │
                              │ draft_section_3_nfr  (par) │
                              │ draft_section_3_iface      │
                              └────────────┬──────────────┘
                                           ↓ (fan-in — all three write to sections)
                                       draft_section_1
                                           ↓
                                       draft_section_2
                                           ↓
                                       draft_section_4
                                           ↓
                                       generate_mermaid
                                           ↓
                                       validate_mermaid
                                       ↙ [errors & retries left]  ↘ [valid]
                               correct_mermaid                  qa_review
                                    ↓                           ↙ [gaps]  ↘ [passed]
                               validate_mermaid    ask_clarifying_questions  finalize_document
                                                                                    ↓
                                                                                  END
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import get_settings
from app.graph.nodes import (
    ask_clarifying_questions,
    classify_requirements,
    correct_mermaid,
    draft_section_1,
    draft_section_2,
    draft_section_3_fr,
    draft_section_3_nfr,
    draft_section_3_iface,
    draft_section_4,
    elicit_requirements,
    evaluate_completeness,
    finalize_document,
    generate_mermaid,
    qa_review,
    retrieve_rag_context,
    validate_mermaid,
)
from app.graph.state import SRSState

logger = logging.getLogger(__name__)

# ── Conditional edge functions ─────────────────────────────────────────────────


def _fan_out_section_3(state: SRSState) -> list[Send]:
    """
    Dispatch three parallel Section-3 writer nodes via LangGraph's Send API.
    Each writer receives the full state and writes to a distinct sections key.
    """
    return [
        Send("draft_section_3_fr", state),
        Send("draft_section_3_nfr", state),
        Send("draft_section_3_iface", state),
    ]


def _route_after_mermaid_validation(
    state: SRSState,
) -> Literal["correct_mermaid", "qa_review"]:
    """Retry correction loop if errors exist and budget not exhausted."""
    settings = get_settings()
    errors = state.get("mermaid_errors", [])
    attempts = state.get("mermaid_correction_attempts", 0)
    has_errors = any(e for e in errors)

    if has_errors and attempts < settings.max_mermaid_retries:
        logger.info(
            "Mermaid errors detected (attempt %d/%d) — routing to corrector.",
            attempts + 1,
            settings.max_mermaid_retries,
        )
        return "correct_mermaid"
    return "qa_review"


def _route_after_qa(
    state: SRSState,
) -> Literal["ask_clarifying_questions", "finalize_document"]:
    """Pause for clarification if draft gaps remain, else finalise."""
    if state.get("missing_context") or not state.get("is_complete", False):
        return "ask_clarifying_questions"
    return "finalize_document"


# ── Graph builder ─────────────────────────────────────────────────────────────


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    """
    Compile and return the LangGraph StateGraph.

    Args:
        checkpointer: A LangGraph checkpointer (e.g., AsyncPostgresSaver).
                      If None the graph runs in-memory without persistence.

    Returns:
        Compiled CompiledGraph ready for ``.ainvoke()`` / ``.astream()``.
    """
    builder = StateGraph(SRSState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("retrieve_rag_context", retrieve_rag_context)
    builder.add_node("elicit_requirements", elicit_requirements)
    builder.add_node("evaluate_completeness", evaluate_completeness)
    builder.add_node("ask_clarifying_questions", ask_clarifying_questions)
    builder.add_node("classify_requirements", classify_requirements)

    # Section 3 parallel writers
    builder.add_node("draft_section_3_fr", draft_section_3_fr)
    builder.add_node("draft_section_3_nfr", draft_section_3_nfr)
    builder.add_node("draft_section_3_iface", draft_section_3_iface)

    # Sequential section writers
    builder.add_node("draft_section_1", draft_section_1)
    builder.add_node("draft_section_2", draft_section_2)
    builder.add_node("draft_section_4", draft_section_4)

    # Diagram pipeline
    builder.add_node("generate_mermaid", generate_mermaid)
    builder.add_node("validate_mermaid", validate_mermaid)
    builder.add_node("correct_mermaid", correct_mermaid)

    # QA and finalisation
    builder.add_node("qa_review", qa_review)
    builder.add_node("finalize_document", finalize_document)

    # ── Wire edges ────────────────────────────────────────────────────────────

    # Entry → elicitation pipeline
    builder.add_edge(START, "retrieve_rag_context")
    builder.add_edge("retrieve_rag_context", "elicit_requirements")
    builder.add_edge("elicit_requirements", "evaluate_completeness")

    # Always draft a best-effort SRS after the first evaluation pass.
    builder.add_edge("evaluate_completeness", "classify_requirements")

    # HITL loop-back: after user answers, re-evaluate
    builder.add_edge("ask_clarifying_questions", "evaluate_completeness")

    # Classification → fan-out to three parallel Section 3 writers
    builder.add_conditional_edges(
        "classify_requirements",
        _fan_out_section_3,
        # No explicit target map needed for Send-based fan-out
    )

    # All three Section 3 writers converge before Section 1
    # (Section 1 needs entities for glossary; drafts are all in state)
    builder.add_edge("draft_section_3_fr", "draft_section_1")
    builder.add_edge("draft_section_3_nfr", "draft_section_1")
    builder.add_edge("draft_section_3_iface", "draft_section_1")

    # Sequential post-classification pipeline
    builder.add_edge("draft_section_1", "draft_section_2")
    builder.add_edge("draft_section_2", "draft_section_4")
    builder.add_edge("draft_section_4", "generate_mermaid")

    # Mermaid pipeline with self-correction loop
    builder.add_edge("generate_mermaid", "validate_mermaid")
    builder.add_conditional_edges(
        "validate_mermaid",
        _route_after_mermaid_validation,
        {
            "correct_mermaid": "correct_mermaid",
            "qa_review": "qa_review",
        },
    )
    builder.add_edge("correct_mermaid", "validate_mermaid")

    # QA → finalise or another HITL round
    builder.add_conditional_edges(
        "qa_review",
        _route_after_qa,
        {
            "ask_clarifying_questions": "ask_clarifying_questions",
            "finalize_document": "finalize_document",
        },
    )

    builder.add_edge("finalize_document", END)

    # ── Compile ───────────────────────────────────────────────────────────────
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["ask_clarifying_questions"],
    )
    logger.info("SRS generator graph compiled successfully.")
    return compiled
