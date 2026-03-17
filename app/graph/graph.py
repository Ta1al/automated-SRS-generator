"""
LangGraph StateGraph definition for the SRS generator workflow.

Optimised topology — critical path is 4 sequential LLM calls:
    START
      → retrieve_rag_context
      → elicit_requirements
      → fan-out (Send) — all 5 section writers run in parallel:
            draft_section_1
            draft_section_2
            draft_section_3_fr
            draft_section_3_nfr
            draft_section_3_iface
      → fan-in → draft_section_4
      → generate_mermaid      (3 diagrams generated via asyncio.gather internally)
      → validate_mermaid
        ↙ [errors & retries left]   ↘ [valid / budget exhausted]
    correct_mermaid             finalize_document
          ↓                              ↓
    validate_mermaid                    END
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import get_settings
from app.graph.nodes import (
    correct_mermaid,
    draft_section_1,
    draft_section_2,
    draft_section_3_fr,
    draft_section_3_nfr,
    draft_section_3_iface,
    draft_section_4,
    elicit_requirements,
    finalize_document,
    generate_mermaid,
    retrieve_rag_context,
    validate_mermaid,
)
from app.graph.state import SRSState

logger = logging.getLogger(__name__)

# ── Conditional edge functions ─────────────────────────────────────────────────


def _fan_out_all_sections(state: SRSState) -> list[Send]:
    """
    Dispatch all five section writer nodes simultaneously via LangGraph's Send API.
    Sections 1, 2, 3-FR, 3-NFR, and 3-Interface are fully independent — each
    reads from state and writes to a distinct key — so they can all run in parallel.
    """
    return [
        Send("draft_section_1", state),
        Send("draft_section_2", state),
        Send("draft_section_3_fr", state),
        Send("draft_section_3_nfr", state),
        Send("draft_section_3_iface", state),
    ]


def _route_after_mermaid_validation(
    state: SRSState,
) -> Literal["correct_mermaid", "finalize_document"]:
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

    # All five section writers run in parallel via Send fan-out
    builder.add_node("draft_section_1", draft_section_1)
    builder.add_node("draft_section_2", draft_section_2)
    builder.add_node("draft_section_3_fr", draft_section_3_fr)
    builder.add_node("draft_section_3_nfr", draft_section_3_nfr)
    builder.add_node("draft_section_3_iface", draft_section_3_iface)

    # Verification matrix — runs after all five writers fan-in
    builder.add_node("draft_section_4", draft_section_4)

    # Diagram pipeline
    builder.add_node("generate_mermaid", generate_mermaid)
    builder.add_node("validate_mermaid", validate_mermaid)
    builder.add_node("correct_mermaid", correct_mermaid)

    # Finalisation
    builder.add_node("finalize_document", finalize_document)

    # ── Wire edges ────────────────────────────────────────────────────────────

    # Entry → elicitation
    builder.add_edge(START, "retrieve_rag_context")
    builder.add_edge("retrieve_rag_context", "elicit_requirements")

    # elicit_requirements → fan-out ALL five section writers in parallel
    builder.add_conditional_edges(
        "elicit_requirements",
        _fan_out_all_sections,
    )

    # All five section writers fan-in to the verification matrix
    builder.add_edge("draft_section_1", "draft_section_4")
    builder.add_edge("draft_section_2", "draft_section_4")
    builder.add_edge("draft_section_3_fr", "draft_section_4")
    builder.add_edge("draft_section_3_nfr", "draft_section_4")
    builder.add_edge("draft_section_3_iface", "draft_section_4")

    # Sequential post-fanin pipeline
    builder.add_edge("draft_section_4", "generate_mermaid")

    # Mermaid pipeline with self-correction loop
    builder.add_edge("generate_mermaid", "validate_mermaid")
    builder.add_conditional_edges(
        "validate_mermaid",
        _route_after_mermaid_validation,
        {
            "correct_mermaid": "correct_mermaid",
            "finalize_document": "finalize_document",
        },
    )
    builder.add_edge("correct_mermaid", "validate_mermaid")

    builder.add_edge("finalize_document", END)

    # ── Compile ───────────────────────────────────────────────────────────────
    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("SRS generator graph compiled successfully.")
    return compiled
