"""
LangGraph state schema for the SRS generator workflow.

All nodes receive the full ``SRSState`` dict and return a partial update.
LangGraph merges the partial update back using the annotated reducers.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def merge_sections(
    current: dict[str, str] | None,
    update: dict[str, str] | None,
) -> dict[str, str]:
    """Reducer for section drafts written by parallel LangGraph nodes."""
    base = dict(current or {})
    if update:
        base.update(update)
    return base


class Requirement(TypedDict):
    """A single atomic requirement extracted from user input."""

    id: str                   # e.g. "F-001", "SE-003"
    text: str                 # The requirement statement
    labels: list[str]         # e.g. ["SE", "L"]
    criteria: str             # Boolean-testable acceptance criterion


class ClarificationQuestion(TypedDict, total=False):
    """A targeted follow-up question needed to complete the SRS."""

    category: str
    question: str
    suggested_options: list[str]
    rationale: str


class SRSState(TypedDict):
    """
    Global state passed through every node in the LangGraph workflow.

    Fields:
        chat_history:
            Full message history between user and AI.  The ``add_messages``
            reducer appends new messages rather than replacing the list.

        document_buffer:
            Raw working draft accumulated by the elicitor node on first pass.

        missing_context:
            List of structured follow-up questions identified by the evaluator node.
            Empty list signals readiness to proceed to drafting.

        requirements:
            Parsed and classified atomic requirements.

        rag_context:
            Retrieved regulatory/standards text injected into prompts.

        sections:
            Keyed Markdown strings for each SRS section.
            Keys: "s1", "s2", "s3_fr", "s3_nfr", "s3_iface", "s4"

        mermaid_blocks:
            Raw Mermaid diagram code strings (without fence markers).

        mermaid_errors:
            Validator error messages aligned by index with mermaid_blocks.
            Empty string means the block at that index is valid.

        mermaid_correction_attempts:
            Counter preventing infinite correction loops.

        generate_diagrams:
            When True, run Mermaid generation/validation before finalizing.
            Default False for normal drafting runs.

        diagrams_only:
            When True, bypass drafting and generate diagrams from existing sections.

        revision_mode:
            When True, bypass full drafting and only revise the selected section.

        revision_target_section_key / revision_target_title / revision_target_content:
            Metadata about the selected section to revise.

        revision_request:
            The user's requested change for the selected section.

        is_complete:
            Boolean flag set by the QA reviewer when the document passes.

        qa_gaps:
            List of structured follow-up questions returned by the QA reviewer when
            is_complete is False.

        final_document:
            Fully assembled, validated Markdown SRS document.

        project_title:
            Short LLM-generated title inferred from the user's prompt.

        major_decisions_asked:
            True after the major-decision clarification round has been asked once.
            Prevents repeated follow-up loops for minor details.
    """

    # ── Conversation ──────────────────────────────────────────────────────────
    chat_history: Annotated[list[BaseMessage], add_messages]

    # ── Elicitation ───────────────────────────────────────────────────────────
    document_buffer: str
    missing_context: list[ClarificationQuestion]

    # ── Requirements ──────────────────────────────────────────────────────────
    requirements: list[Requirement]

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_context: str

    # ── Section drafts ────────────────────────────────────────────────────────
    sections: Annotated[dict[str, str], merge_sections]

    # ── Mermaid ───────────────────────────────────────────────────────────────
    mermaid_blocks: list[str]
    mermaid_errors: list[str]
    mermaid_correction_attempts: int
    generate_diagrams: bool
    diagrams_only: bool
    revision_mode: bool

    # ── Targeted revision ────────────────────────────────────────────────────
    revision_target_section_key: str
    revision_target_title: str
    revision_target_content: str
    revision_request: str

    # ── Quality assurance ─────────────────────────────────────────────────────
    is_complete: bool
    qa_gaps: list[ClarificationQuestion]
    major_decisions_asked: bool

    # ── Final output ──────────────────────────────────────────────────────────
    final_document: str
    project_title: str
