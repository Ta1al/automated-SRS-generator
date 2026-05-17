"""
LangGraph state schema for the SRS generator workflow.

Phases:
1. Ingestion: Parse informal input, extract domain/actors/platform needs
2. Elicitation: Interactive Q&A with 4 grouped batches (roles, boundaries, NFRs, edge cases)
3. Drafting: Synthesize into formal SRS sections via parallel drafters
4. Diagram generation & finalization

All nodes receive the full ``SRSState`` dict and return a partial update.
LangGraph merges the partial update back using the annotated reducers.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

try:
    from typing import TypedDict  # Python >=3.8
except ImportError:
    from typing_extensions import TypedDict  # Python 3.7


def merge_sections(
    current: dict[str, str] | None,
    update: dict[str, str] | None,
) -> dict[str, str]:
    """Reducer for section drafts written by parallel LangGraph nodes."""
    base = dict(current or {})
    if update:
        base.update(update)
    return base


def merge_dicts(
    current: dict[str, Any] | None,
    update: dict[str, Any] | None,
) -> dict[str, Any]:
    """Generic dict merger for accumulating answers or metadata."""
    base = dict(current or {})
    if update:
        base.update(update)
    return base


def merge_lists(
    current: list[Any] | None,
    update: list[Any] | None,
) -> list[Any]:
    """Reducer for lists: extend if update provided, otherwise keep current."""
    if update is None:
        return current or []
    return update


# ─────────────────────────────────────────────────────────────────────────────
# TypedDicts for Structured Data
# ─────────────────────────────────────────────────────────────────────────────


class CoreFlow(TypedDict, total=False):
    """A single core flow with goal, steps, and success metric."""
    name: str
    goal: str
    steps: list[str]
    success_metric: str


class IngestionSummary(TypedDict, total=False):
    """Normalized intake summary from user's initial informal product idea."""
    project_title: str
    domain: str
    project_purpose: str
    target_users: list[str]
    suggested_actors: list[str]
    platform_needs: list[str]
    success_criteria: list[str]
    architecture_summary: str
    components: list[str]
    core_flows: list[CoreFlow]
    data_entities: list[str]
    external_interfaces: list[str]
    constraints: list[str]
    assumptions: list[str]


class ClarificationQuestion(TypedDict, total=False):
    """A targeted follow-up question in the elicitation phase."""
    category: str  # e.g., "User Roles", "Functional Boundaries", "NFRs", "Edge Cases"
    group: int  # 0-3 mapping to elicitation groups
    priority: str  # e.g., "high", "medium", "low"
    question: str
    suggested_options: list[str]
    rationale: str


class Requirement(TypedDict, total=False):
    """A single atomic requirement extracted from user input."""
    id: str  # e.g., "F-001", "SE-003"
    text: str
    labels: list[str]  # e.g., ["Functional", "Security"]
    criteria: str  # Boolean-testable acceptance criterion


# ─────────────────────────────────────────────────────────────────────────────
# Main SRSState
# ─────────────────────────────────────────────────────────────────────────────


class SRSState(TypedDict):
    """
    Global state passed through every node in the 5-phase LangGraph workflow.

    Phase Tracking:
        current_phase: Enum tracking which phase the workflow is in
        
    Ingestion & Elicitation:
        ingestion_summary: Extracted domain, actors, platform needs from initial input
        pending_group_index: Current elicitation group index (0-3, or 4 = all complete)
        elicitation_answers: Accumulated answers from user across all 4 Q&A groups
        
    Drafting & Sections:
        sections: Keyed Markdown strings for each SRS section
                 Keys: "s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"
        
    Diagrams:
        plantumul_diagrams: PlantUML diagram code (use case, etc.)
        mermaid_blocks: Mermaid diagram code strings (ER, activity, dataflow)
        
    Review:
        revision_targets: List of section keys user wants to regenerate
        
    History & Context:
        chat_history: Full message history between user and AI
        requirements: Parsed requirements extracted from conversation
        rag_context: Retrieved regulatory/standards text injected into prompts
    """

    # ────────────────────────────────────────────────────────────────────────
    # Phase tracking
    # ────────────────────────────────────────────────────────────────────────
    current_phase: str  # "ingestion" | "elicitation" | "drafting" | "complete"

    # ────────────────────────────────────────────────────────────────────────
    # Ingestion & Elicitation
    # ────────────────────────────────────────────────────────────────────────
    ingestion_summary: Annotated[dict[str, Any], merge_dicts]
    pending_group_index: int  # Current elicitation group (0-3, or 4 = complete)
    elicitation_answers: Annotated[dict[str, Any], merge_dicts]  # group_0, group_1, group_2, group_3 answers
    elicitation_question_plan: Annotated[list[str], merge_lists]  # Question topics for current group
    elicitation_question_index: int  # Current question number within group

    # ────────────────────────────────────────────────────────────────────────
    # Sections & Drafts
    # ────────────────────────────────────────────────────────────────────────
    sections: Annotated[dict[str, str], merge_sections]  # s1, s2, s3_functional, s3_external, s3_nfr, s4
    section_structures: Annotated[dict[str, list[dict]], merge_sections]  # Structured subsections: {key: [{number, title, content}, ...]}

    # ────────────────────────────────────────────────────────────────────────
    # Diagrams
    # ────────────────────────────────────────────────────────────────────────
    plantumul_diagrams: Annotated[dict[str, str], merge_dicts]  # "usecase", etc.
    mermaid_blocks: Annotated[list[str], merge_lists]  # ER, activity, dataflow diagrams
    mermaid_errors: Annotated[list[str], merge_lists]  # Validation errors aligned with mermaid_blocks

    # ────────────────────────────────────────────────────────────────────────
    # Review & Refine
    # ────────────────────────────────────────────────────────────────────────
    revision_targets: Annotated[list[str], merge_lists]  # Sections user wants to regenerate
    revision_mode: bool  # True when running a section revision
    revision_target_section_key: str  # Which section to revise (s1, s2, s3_functional, etc.)
    revision_target_title: str  # Display title of the section being revised
    revision_target_content: str  # Original content of the section being revised
    revision_request: str  # User's revision request/feedback
    is_complete: bool  # Whether the workflow is complete
    generate_diagrams: bool  # Whether diagrams should be generated
    diagrams_only: bool  # Whether running in diagrams-only mode
    final_document: str  # Final assembled SRS document
    project_title: str  # Project title
    qa_gaps: Annotated[list[Any], merge_lists]
    major_decisions_asked: bool
    document_buffer: str
    missing_context: Annotated[list[Any], merge_lists]

    # ────────────────────────────────────────────────────────────────────────
    # Conversation history & context
    # ────────────────────────────────────────────────────────────────────────
    chat_history: Annotated[list[BaseMessage], add_messages]
    requirements: Annotated[list[Requirement], merge_lists]
    rag_context: str  # Retrieved standards/regulatory text for prompting
