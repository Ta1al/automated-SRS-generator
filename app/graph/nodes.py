"""
LangGraph node functions for the 5-phase SRS generator workflow.

Uses LangChain's structured output (with_structured_output) to ensure
the LLM returns properly formatted data matching Pydantic models.

Each node accepts the full ``SRSState`` and returns a partial dict that
LangGraph merges back into the shared state via the declared reducers.

Convention:
    async def node_name(state: SRSState) -> dict
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings
from app.formatting import assemble_document_from_sections
from app.graph import prompts
from app.graph.state import SRSState, IngestionSummary, ClarificationQuestion
from app.rag.vectorstore import retrieve
from app.validation.mermaid import validate_mermaid_syntax

logger = logging.getLogger(__name__)

settings = get_settings()




def _latest_human_message(state: SRSState) -> HumanMessage | None:
    for message in reversed(state.get("chat_history", [])):
        if isinstance(message, HumanMessage):
            return message
    return None


def _normalize_message_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _is_control_command(message_text: str, command: str) -> bool:
    return _normalize_message_text(message_text) == command


def _build_plantuml_diagrams(ingestion: dict[str, Any]) -> dict[str, str]:
    def _sanitize_identifier(value: Any, fallback: str) -> str:
        text = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "")).strip("_")
        return text or fallback

    def _first_text(values: list[Any], fallback: str) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return fallback

    project_title = str(ingestion.get("project_title", "System")).strip() or "System"
    actors = [str(actor).strip() for actor in (ingestion.get("suggested_actors", []) or ingestion.get("target_users", []) or ["User"]) if str(actor).strip()]
    flows = [flow for flow in (ingestion.get("core_flows", []) or []) if isinstance(flow, dict)]
    components = [str(component).strip() for component in (ingestion.get("components", []) or []) if str(component).strip()]
    entities = [str(entity).strip() for entity in (ingestion.get("data_entities", []) or []) if str(entity).strip()]
    interfaces = [str(interface).strip() for interface in (ingestion.get("external_interfaces", []) or []) if str(interface).strip()]
    primary_flow_name = _first_text([flow.get("name") for flow in flows], "Primary Workflow")
    primary_flow_goal = _first_text([flow.get("goal") for flow in flows], "Process the user's request")
    primary_actor = actors[0] if actors else "User"
    support_actor = actors[1] if len(actors) > 1 else "Admin"
    ui_component = components[0] if components else "User Interface"
    service_component = components[1] if len(components) > 1 else "Application Service"
    data_component = components[2] if len(components) > 2 else "Data Store"

    actor_lines = "\n".join(
        f'actor "{actor}" as {_sanitize_identifier(actor, f"Actor{i + 1}")}'
        for i, actor in enumerate(actors[:4])
    )
    usecase_lines = "\n".join(
        f'  usecase "{str(flow.get("name", f"Use Case {i + 1}")).strip()}" as UC{i + 1}'
        for i, flow in enumerate(flows[:6])
    )
    relation_lines = [
        f'  {_sanitize_identifier(primary_actor, "Actor1")} --> UC1',
    ]
    if len(flows) > 1 and len(actors) > 1:
        relation_lines.append(f'  {_sanitize_identifier(support_actor, "Actor2")} --> UC2')
    if len(flows) > 2:
        relation_lines.append(f'  UC1 ..> UC3 : includes')
    if len(flows) > 3:
        relation_lines.append(f'  UC2 ..> UC4 : extends')
    usecase_diagram = (
        "@startuml\n"
        "left to right direction\n"
        f'title {project_title} Use Case Overview\n'
        f'{actor_lines}\n'
        f'\nrectangle "{project_title}" {{\n'
        f'{usecase_lines}\n'
        "}\n"
        f'{"\n".join(relation_lines)}\n'
        "@enduml"
    )

    component_interfaces = "\n".join(
        f'component "{name}" as {_sanitize_identifier(name, f"Component{i + 1}")}'
        for i, name in enumerate((components[:3] or [ui_component, service_component, data_component]))
    )
    external_nodes = "\n".join(
        f'cloud "{name}" as {_sanitize_identifier(name, f"External{i + 1}")}'
        for i, name in enumerate(interfaces[:3])
    )
    component_diagram = (
        "@startuml\n"
        f'title {project_title} Context and Components\n'
        f'{component_interfaces}\n'
        f'{external_nodes}\n'
        f'{_sanitize_identifier(ui_component, "Component1")} --> {_sanitize_identifier(service_component, "Component2")}\n'
        f'{_sanitize_identifier(service_component, "Component2")} --> {_sanitize_identifier(data_component, "Component3")}\n'
        + (f'{_sanitize_identifier(service_component, "Component2")} --> {_sanitize_identifier(interfaces[0], "External1")}\n' if interfaces else "")
        + "@enduml"
    )

    sequence_diagram = (
        "@startuml\n"
        f'title {project_title} - {primary_flow_name}\n'
        f'actor "{primary_actor}" as {_sanitize_identifier(primary_actor, "Actor1")}\n'
        f'participant "{ui_component}" as UI\n'
        f'participant "{service_component}" as APP\n'
        f'participant "{data_component}" as DB\n'
        + (f'participant "{interfaces[0]}" as EXT\n' if interfaces else "")
        + f'{_sanitize_identifier(primary_actor, "Actor1")} -> UI: Start {primary_flow_name.lower()}\n'
        f'UI -> APP: Submit request\n'
        f'APP -> DB: Persist / validate data\n'
        + (f'APP -> EXT: Call external service\n' if interfaces else "")
        + f'APP --> UI: Confirmation\n'
        f'UI --> {_sanitize_identifier(primary_actor, "Actor1")} : Show result\n'
        "@enduml"
    )

    activity_diagram = (
        "@startuml\n"
        f'title {project_title} Workflow\n'
        "start\n"
        f':{primary_flow_name};\n'
        f':{primary_flow_goal};\n'
        "if (Valid input?) then (yes)\n"
        "  :Process request;\n"
        "  :Store outcome;\n"
        "else (no)\n"
        "  :Return validation feedback;\n"
        "endif\n"
        "stop\n"
        "@enduml"
    )

    return {
        "usecase": usecase_diagram,
        "component": component_diagram,
        "sequence": sequence_diagram,
        "activity": activity_diagram,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models for Structured Output
# ─────────────────────────────────────────────────────────────────────────────

class IngestionSummaryModel(BaseModel):
    """Normalized intake summary from user's initial product idea."""
    project_title: str = Field(..., description="Project name")
    domain: str = Field(..., description="Business domain")
    project_purpose: str = Field(..., description="What the system achieves")
    target_users: list[Any] | str | Any = Field(default=[], description="Primary user types")
    suggested_actors: list[Any] | str | Any = Field(default=[], description="System actors/roles")
    platform_needs: list[Any] | str | Any = Field(default=[], description="Delivery platforms")
    success_criteria: list[Any] | str | Any = Field(default=[], description="Success criteria")
    architecture_summary: str = Field(default="", description="High-level architecture")
    components: list[Any] | str | Any = Field(default=[], description="Major components")
    core_flows: list[Any] | str | Any = Field(default=[], description="Core user workflows")
    data_entities: list[Any] | str | Any = Field(default=[], description="Core data entities")
    external_interfaces: list[Any] | str | Any = Field(default=[], description="External integrations")
    constraints: list[Any] | str | Any = Field(default=[], description="Known constraints")
    assumptions: list[Any] | str | Any = Field(default=[], description="Key assumptions")


class ClarificationQuestionModel(BaseModel):
    """A targeted follow-up question."""
    category: str = Field(..., description="Question category")
    group: int = Field(..., description="Group index 0-3")
    question: str = Field(..., description="The question itself")
    suggested_options: list[str] = Field(default_factory=list, description="2-3 example answers")
    rationale: str = Field(..., description="Why we need this info")


class QuestionPlanModel(BaseModel):
    """Plan: list of question topics for a group."""
    topics: list[str] = Field(..., description="2-3 question topics")

    @model_validator(mode="before")
    @classmethod
    def _coerce_singular_topic(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "topics" not in data and "topic" in data:
                coerced = dict(data)
                topic_value = coerced.get("topic")
                if isinstance(topic_value, list):
                    coerced["topics"] = topic_value
                elif isinstance(topic_value, str) and topic_value.strip():
                    coerced["topics"] = [topic_value.strip()]
                return coerced
        return data


class ElicitationQuestionListModel(BaseModel):
    """List of elicitation questions for a group."""
    questions: list[ClarificationQuestionModel] = Field(..., description="Questions for this group")


class SubsectionContent(BaseModel):
    """A single subsection with explicit numbering, title, and markdown content."""
    number: str = Field(..., description="Subsection number (e.g. '1.1', '3.2.1')")
    title: str = Field(..., description="Subsection title (e.g. 'Purpose', 'User Interfaces')")
    content: str = Field(..., description="Full Markdown content for this subsection, excluding the heading")


class DraftSectionModel(BaseModel):
    """A drafted SRS section with subsections separated into structured fields."""
    subsections: list[SubsectionContent] = Field(..., description="All subsections for this SRS section")


class MermaidDiagramSet(BaseModel):
    """Set of 4 Mermaid diagrams for the SRS document."""
    usecase: str = Field(..., description="Mermaid use case diagram code")
    class_diagram: str = Field(..., description="Mermaid class diagram code")
    er: str = Field(..., description="Mermaid ER diagram code")
    activity: str = Field(..., description="Mermaid activity/state diagram code")

    @model_validator(mode="before")
    @classmethod
    def _normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalized = dict(data)
            if "class" in normalized and "class_diagram" not in normalized:
                normalized["class_diagram"] = normalized.pop("class")
            return normalized
        return data


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


async def _llm_invoke_structured(
    system_prompt: str,
    output_model: type[BaseModel],
    user_message: str | None = None,
    chat_history: list | None = None,
    temperature: float = 0.5,
    max_tokens: int | None = None,
    max_retries: int = 2,
) -> BaseModel:
    """
    Invoke LLM with structured output binding.
    
    Returns a Pydantic model instance matching the output_model schema.
    Includes retry logic for validation errors and dumps raw output on failure.
    
    Args:
        system_prompt: System message
        output_model: Pydantic model to structure the response
        user_message: Optional user message
        chat_history: Optional message history
        temperature: Sampling temperature
        max_tokens: Maximum tokens for response (None = unlimited)
        max_retries: Number of retries on validation failure
    """
    llm = ChatOpenAI(
        model=settings.model_name,
        temperature=temperature,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        max_tokens=max_tokens or 8192,
    )

    # Bind structured output
    llm_structured = llm.with_structured_output(output_model, method="json_mode")

    messages = []

    # Add system prompt
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    # Add conversation history
    if chat_history:
        messages.extend(chat_history)

    # Add current user message
    if user_message:
        messages.append(HumanMessage(content=user_message))

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = await llm_structured.ainvoke(messages)
            return response
        except Exception as e:
            last_error = e
            error_str = str(e)
            
            if attempt < max_retries:
                logger.warning(
                    f"Structured output failed (attempt {attempt + 1}/{max_retries + 1}): {error_str[:200]}. "
                    f"Retrying with adjusted temperature..."
                )
                # Retry with slightly lower temperature for more deterministic output
                llm = ChatOpenAI(
                    model=settings.model_name,
                    temperature=max(0.1, temperature - 0.1),
                    base_url=settings.openrouter_base_url,
                    api_key=settings.openrouter_api_key,
                    max_tokens=max_tokens or 8192,
                )
                llm_structured = llm.with_structured_output(output_model, method="json_mode")
            else:
                logger.error(f"Structured output failed after {max_retries + 1} attempts: {error_str}")
                raise

    # Should not reach here, but just in case
    raise last_error


async def _llm_invoke_text(
    system_prompt: str,
    user_message: str | None = None,
    chat_history: list | None = None,
    temperature: float = 0.7,
) -> str:
    """Invoke LLM without structured output (returns plain text)."""
    llm = ChatOpenAI(
        model=settings.model_name,
        temperature=temperature,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    )

    messages = []

    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    if chat_history:
        messages.extend(chat_history)

    if user_message:
        messages.append(HumanMessage(content=user_message))

    response = await llm.ainvoke(messages)
    return response.content


def _assemble_section_markdown(
    section_key: str,
    subsections: list[SubsectionContent],
) -> str:
    """Assemble structured subsections into a single Markdown string."""
    
    section_headings: dict[str, str] = {
        "s1": "# 1 Introduction",
        "s2": "# 2 Overall Description",
        "s3_functional": "# 3 Specific Requirements\n## 3.1 Functional Requirements",
        "s3_external": "## 3.2 External Interface Requirements",
        "s3_nfr": "## 3.3 Non-functional Requirements",
        "s4": "# 4 Appendices",
    }
    prefix = section_headings.get(section_key, "")

    heading_level = "###" if section_key in ("s3_functional", "s3_external", "s3_nfr") else "##"
    parts = [prefix] if prefix else []
    for sub in subsections:
        parts.append(f"{heading_level} {sub.number} {sub.title}")
        parts.append(sub.content.strip())
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Ingestion
# ─────────────────────────────────────────────────────────────────────────────


async def ingest_and_map_domain(state: SRSState) -> dict:
    """
    Phase 1: Parse user's informal product description and extract domain mapping.
    
    Uses structured output to ensure IngestionSummaryModel is returned.
    """
    logger.info("=== INGESTION PHASE ===")

    # Get user's initial message
    user_messages = [msg for msg in state.get("chat_history", []) if isinstance(msg, HumanMessage)]
    if not user_messages:
        return {"current_phase": "ingestion", "ingestion_summary": {}}

    initial_input = user_messages[0].content

    # Call LLM with structured output
    response = await _llm_invoke_structured(
        system_prompt=prompts.INGESTION_SYSTEM,
        output_model=IngestionSummaryModel,
        user_message=initial_input,  # Ingestion is comprehensive
    )

    # Convert Pydantic model to dict
    ingestion_data = response.model_dump(mode="json")

    logger.info(f"Ingestion summary extracted: {ingestion_data.get('domain', 'unknown')}")

    # Format for display
    summary_text = json.dumps(ingestion_data, indent=2)

    return {
        "current_phase": "elicitation",
        "ingestion_summary": ingestion_data,
        "project_title": str(ingestion_data.get("project_title", "")).strip(),
        "pending_group_index": 0,
        "chat_history": state["chat_history"]
        + [AIMessage(content=f"**✓ Ingestion Complete**\n\nDomain: **{ingestion_data.get('domain', 'Unknown')}**\n"
                           f"Project: {ingestion_data.get('project_title', '')}\n"
                           f"Key actors: {', '.join(ingestion_data.get('suggested_actors', []))}")],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Elicitation (One Question at a Time)
# ─────────────────────────────────────────────────────────────────────────────


async def generate_elicitation_plan(state: SRSState) -> dict:
    """
    Generate a question plan (list of 2-3 topics) for current group.
    
    This plan is lightweight and helps guide single-question generation.
    If all questions in current group are done, advance to next group.
    """
    group_index = state.get("pending_group_index", 0)
    question_index = state.get("elicitation_question_index", 0)
    question_plan = state.get("elicitation_question_plan", [])

    # If we've asked all questions in current plan, move to next group
    if question_index >= len(question_plan) and question_index > 0:
        group_index += 1
        if group_index >= 4:
            return {"pending_group_index": 4, "elicitation_question_index": 0}

    if group_index >= 4:
        return {"pending_group_index": 4, "elicitation_question_index": 0}

    ingestion = state.get("ingestion_summary", {})

    # Select prompt for current group
    plan_prompts = [
        prompts.ELICITATION_PLAN_0_SYSTEM,
        prompts.ELICITATION_PLAN_1_SYSTEM,
        prompts.ELICITATION_PLAN_2_SYSTEM,
        prompts.ELICITATION_PLAN_3_SYSTEM,
    ]
    
    group_titles = [
        "User Roles & Flows",
        "Functional Boundaries",
        "Non-Functional Requirements",
        "Edge Cases & Risk Mitigation"
    ]

    system_prompt = plan_prompts[group_index].format(
        ingestion_summary=json.dumps(ingestion, indent=2),
    )

    logger.info(f"Generating elicitation plan for group {group_index}: {group_titles[group_index]}")

    # Get question plan (lightweight)
    response = await _llm_invoke_structured(
        system_prompt=system_prompt,
        output_model=QuestionPlanModel,
    )

    topics = response.topics
    logger.info(f"Plan for group {group_index}: {topics}")

    return {
        "pending_group_index": group_index,
        "elicitation_question_plan": topics,
        "elicitation_question_index": 0,
    }


async def generate_single_elicitation_question(state: SRSState) -> dict:
    """
    Generate a single elicitation question based on current plan topic.
    
    Ask one question, then interrupt for user response.
    """
    group_index = state.get("pending_group_index", 0)
    question_index = state.get("elicitation_question_index", 0)
    question_plan = state.get("elicitation_question_plan", [])
    ingestion = state.get("ingestion_summary", {})

    sections = state.get("sections", {})
    if isinstance(sections, dict) and len([key for key in ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"] if sections.get(key)]) >= 6:
        final_document = assemble_document_from_sections(sections)
        return {
            "current_phase": "complete",
            "is_complete": True,
            "final_document": final_document,
            "project_title": str(ingestion.get("project_title", "")).strip(),
            "plantumul_diagrams": _build_plantuml_diagrams(ingestion),
        }

    if question_index >= len(question_plan):
        # All questions in this group asked, move to next group or outline
        next_group_index = group_index + 1
        if next_group_index >= 4:
            return {"pending_group_index": 4}
        else:
            return {"pending_group_index": next_group_index}

    topic = question_plan[question_index]

    # Select prompt for current group
    single_question_prompts = [
        prompts.ELICITATION_SINGLE_QUESTION_0_SYSTEM,
        prompts.ELICITATION_SINGLE_QUESTION_1_SYSTEM,
        prompts.ELICITATION_SINGLE_QUESTION_2_SYSTEM,
        prompts.ELICITATION_SINGLE_QUESTION_3_SYSTEM,
    ]

    group_titles = [
        "User Roles & Flows",
        "Functional Boundaries",
        "Non-Functional Requirements",
        "Edge Cases & Risk Mitigation"
    ]

    system_prompt = single_question_prompts[group_index].format(
        ingestion_summary=json.dumps(ingestion, indent=2),
        topic=topic,
    )

    logger.info(f"Generating question {question_index + 1}/{len(question_plan)} for group {group_index}")

    # Get single question
    response = await _llm_invoke_structured(
        system_prompt=system_prompt,
        output_model=ClarificationQuestionModel,
    )

    question = response

    # Format as message
    question_text = f"**Q{question_index + 1}. {question.question}**"
    if question.suggested_options:
        options_text = "\n".join([f"- {opt}" for opt in question.suggested_options])
        question_text += f"\n\n{options_text}"

    logger.info(f"Question for group {group_index}: {question.question[:100]}...")

    # Pause to wait for user answer - use frontend-compatible format
    human_answer = interrupt({
        "type": "clarification_needed",
        "group": group_index,
        "prompt": f"Group {group_index + 1}: {group_titles[group_index]} (Q{question_index + 1}/{len(question_plan)})",
        "questions": [question.model_dump(mode="json")],
    })

    answer_text = ""
    if isinstance(human_answer, dict):
        answer_text = str(human_answer.get("message", "")).strip()
    else:
        answer_text = str(human_answer or "").strip()

    new_messages = state.get("chat_history", []) + [
        AIMessage(content=question_text)
    ]
    if answer_text:
        new_messages.append(HumanMessage(content=answer_text))

    return {
        "chat_history": new_messages,
        "elicitation_question_index": question_index + 1,  # Advance to next question
    }


async def classify_and_store_answers(state: SRSState) -> dict:
    """
    Parse and store the latest user answer to the current elicitation group.
    This node runs after each single question to accumulate answers.
    """
    group_index = state.get("pending_group_index", 0)
    latest_message = state.get("chat_history", [])[-1] if state.get("chat_history") else None

    if not isinstance(latest_message, HumanMessage):
        logger.warning("No user message found; skipping classification")
        return {"pending_group_index": group_index + 1}

    user_response = latest_message.content

    # Store answer
    elicitation_answers = state.get("elicitation_answers", {})
    elicitation_answers[f"group_{group_index}"] = {"response": user_response}

    logger.info(f"Stored answers for group {group_index}")

    # Confirmation message
    confirmation = f"Got it! I've noted your answers for {['User Roles & Flows', 'Functional Boundaries', 'Non-Functional Requirements', 'Edge Cases'][group_index]}."

    if group_index < 3:
        confirmation += " Let me continue with the next question..."
    else:
        confirmation += " Now drafting your SRS sections..."

    new_messages = state.get("chat_history", []) + [AIMessage(content=confirmation)]

    return {
        "elicitation_answers": elicitation_answers,
        "chat_history": new_messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Outline Review
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Drafting
# ─────────────────────────────────────────────────────────────────────────────


async def draft_from_approved_outline(state: SRSState) -> dict:
    """
    Dispatch to 6 parallel section drafters once outline is approved.
    """
    logger.info("Starting parallel section drafting")

    ingestion = state.get("ingestion_summary", {})
    elicitation = state.get("elicitation_answers", {})
    outline = state.get("outline_items", [])
    chat_history_str = "\n".join([
        f"{msg.__class__.__name__}: {msg.content[:80]}" 
        for msg in state.get("chat_history", [])
    ])

    # Prepare context for all drafters
    context = {
        "outline": json.dumps(outline, indent=2),
        "ingestion_summary": json.dumps(ingestion, indent=2),
        "elicitation_answers": json.dumps(elicitation, indent=2),
        "chat_history": chat_history_str,
    }

    # Run all 6 drafters in parallel using structured output with subsection fields
    async def draft_section(section_key: str, prompt_template: str) -> tuple[str, str, list[dict]]:
        prompt = prompt_template.format(**context)
        result = await _llm_invoke_structured(
            system_prompt=prompt,
            output_model=DraftSectionModel,
            temperature=0.6,
        )
        markdown = _assemble_section_markdown(section_key, result.subsections)
        structured = [s.model_dump() for s in result.subsections]
        return section_key, markdown, structured

    drafters = [
        ("s1", prompts.DRAFT_SECTION_1_SYSTEM),
        ("s2", prompts.DRAFT_SECTION_2_SYSTEM),
        ("s3_functional", prompts.DRAFT_SECTION_3_FUNCTIONAL_SYSTEM),
        ("s3_external", prompts.DRAFT_SECTION_3_EXTERNAL_SYSTEM),
        ("s3_nfr", prompts.DRAFT_SECTION_3_NFR_SYSTEM),
        ("s4", prompts.DRAFT_SECTION_4_SYSTEM),
    ]

    results = await asyncio.gather(*[draft_section(key, prompt) for key, prompt in drafters])

    sections: dict[str, str] = {}
    section_structures: dict[str, list[dict]] = {}
    for key, markdown, structured in results:
        sections[key] = markdown
        section_structures[key] = structured

    logger.info(f"Completed drafting all sections with structured subsections")

    draft_message = (
        "**✓ SRS Draft Complete**\n\n"
        "The draft has been generated. Check the **SRS Draft** section on the right to review it."
    )

    new_messages = state.get("chat_history", []) + [AIMessage(content=draft_message)]

    return {
        "sections": sections,
        "section_structures": section_structures,
        "current_phase": "drafting",
        "chat_history": new_messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3b: Section Revision (targeted edit of a single section)
# ─────────────────────────────────────────────────────────────────────────────


async def revise_selected_section(state: SRSState) -> dict:
    """
    Revise a single SRS section based on user feedback.

    Reads revision params from state and uses the LLM to regenerate
    only the targeted section, leaving all other sections intact.
    """
    section_key = state.get("revision_target_section_key", "")
    original_content = state.get("revision_target_content", "")
    feedback = state.get("revision_request", "")
    target_title = state.get("revision_target_title", "")
    ingestion = state.get("ingestion_summary", {})
    elicitation = state.get("elicitation_answers", {})

    chat_history_str = "\n".join([
        f"{msg.__class__.__name__}: {msg.content[:200]}"
        for msg in state.get("chat_history", [])
    ])

    if not section_key or not original_content:
        logger.warning("revision_target_section_key or revision_target_content missing; skipping revision")
        return {}

    logger.info(f"Revising section {section_key}: {target_title}")

    system_prompt = prompts.REGENERATION_SYSTEM.format(
        original_section=original_content,
        feedback=feedback,
        ingestion_summary=json.dumps(ingestion, indent=2),
        elicitation_answers=json.dumps(elicitation, indent=2),
        chat_history=chat_history_str,
    )

    revised_content = await _llm_invoke_text(
        system_prompt=system_prompt,
        temperature=0.5,
    )

    revised_content = revised_content.strip()
    if not revised_content:
        logger.warning("Revision returned empty content; keeping original")
        return {}

    sections = dict(state.get("sections", {}))
    sections[section_key] = revised_content

    confirmation = (
        f"**✓ Section Revised: {target_title}**\n\n"
        f"I've updated the section based on your feedback. "
        f"Review it in the right panel and let me know if you need further changes."
    )

    new_messages = list(state.get("chat_history", [])) + [AIMessage(content=confirmation)]

    logger.info(f"Section {section_key} revised successfully")

    return {
        "sections": sections,
        "current_phase": "drafting",
        "chat_history": new_messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Mermaid Diagram Generation
# ─────────────────────────────────────────────────────────────────────────────


def _clean_text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value else fallback


def _item_str(item: Any) -> str:
    if isinstance(item, dict):
        return _clean_text(item.get("name")) or _clean_text(item.get("title")) or str(item)
    return _clean_text(item, str(item))


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _sanitize_id(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label).strip("_")
    return safe or "Entity"


def _escape_label(label: str) -> str:
    l = str(label).strip()
    if not l:
        return ""
    if any(c in l for c in "\"()[]{}:;"):
        return f'"{l}"'
    return l


def _build_diagram_hints(ingestion: dict[str, Any]) -> str:
    parts: list[str] = []
    actors = _coerce_list(ingestion.get("suggested_actors", []) or ingestion.get("target_users", []))
    flows = [f for f in _coerce_list(ingestion.get("core_flows", [])) if isinstance(f, dict)]
    entities = _coerce_list(ingestion.get("data_entities", []))
    components = _coerce_list(ingestion.get("components", []))
    interfaces = _coerce_list(ingestion.get("external_interfaces", []))

    if actors:
        parts.append(f"Actors (up to 6): {', '.join(_item_str(a) for a in actors[:6])}")
    if flows:
        flow_lines = []
        for f in flows[:4]:
            name = _clean_text(f.get("name"), f"Flow {flows.index(f) + 1}")
            goal = _clean_text(f.get("goal"))
            steps = _coerce_list(f.get("steps", []))
            entry = name
            if goal:
                entry += f" — {goal}"
            if steps:
                entry += f" [{'; '.join(steps[:3])}]"
            flow_lines.append(entry)
        parts.append("Key workflows: " + " | ".join(flow_lines))
    if entities:
        parts.append(f"Data entities: {', '.join(_item_str(e) for e in entities[:8])}")
    if components:
        parts.append(f"System components: {', '.join(_item_str(c) for c in components[:6])}")
    if interfaces:
        parts.append(f"External integrations: {', '.join(_item_str(i) for i in interfaces[:6])}")
    return "\n".join(parts) if parts else "No additional hints available."


async def generate_mermaid_diagrams(state: SRSState) -> dict:
    """
    Generate 4 Mermaid diagrams (usecase, class, ER, activity) using the LLM
    based on ingestion summary, elicitation answers, and drafted sections.
    """
    ingestion = state.get("ingestion_summary", {})
    elicitation = state.get("elicitation_answers", {})
    sections = state.get("sections", {})

    sections_preview = "\n\n".join(
        f"### {key}\n{content[:500]}"
        for key, content in sections.items()
        if content
    )[:3000]

    diagram_hints = _build_diagram_hints(ingestion)

    system_prompt = prompts.MERMAID_GENERATION_SYSTEM.format(
        ingestion_summary=json.dumps(ingestion, indent=2),
        elicitation_answers=json.dumps(elicitation, indent=2),
        sections=sections_preview,
        diagram_hints=diagram_hints,
    )

    logger.info("Generating Mermaid diagrams")

    try:
        response = await _llm_invoke_structured(
            system_prompt=system_prompt,
            output_model=MermaidDiagramSet,
            temperature=0.4,
            max_tokens=4096,
        )

        diagram_code = response.model_dump(mode="json")
        fallback_blocks = _build_mermaid_diagrams(ingestion)
        mermaid_blocks: list[str] = []
        mermaid_errors: list[str] = []

        diagram_type_prefixes = {
            "usecase": "flowchart TD",
            "class_diagram": "classDiagram",
            "er": "erDiagram",
            "activity": "stateDiagram-v2",
        }

        for index, (key, expected_prefix) in enumerate(diagram_type_prefixes.items()):
            code = str(diagram_code.get(key, "")).strip()
            if code.startswith("usecaseDiagram"):
                # Mermaid has no native usecaseDiagram type; fallback to flowchart.
                code = ""
            if not code:
                code = fallback_blocks[index]
            elif not code.startswith(expected_prefix):
                code = f"{expected_prefix}\n{code}"

            is_valid, validation_error = await validate_mermaid_syntax(code)
            if not is_valid:
                mermaid_errors.append(f"{key}: {validation_error}")
                code = fallback_blocks[index]

            mermaid_blocks.append(code)

        if not mermaid_blocks:
            mermaid_blocks = fallback_blocks

        logger.info(f"Generated {len(mermaid_blocks)} Mermaid diagrams")
        return {"mermaid_blocks": mermaid_blocks, "mermaid_errors": mermaid_errors}

    except Exception as exc:
        logger.warning(f"Mermaid diagram generation failed: {exc}. Using fallback.")
        mermaid_blocks = _build_mermaid_diagrams(ingestion)
        return {"mermaid_blocks": mermaid_blocks, "mermaid_errors": [str(exc)]}


def _build_mermaid_diagrams(ingestion: dict) -> list[str]:
    """Generate fallback Mermaid diagrams when LLM generation fails."""
    project_title = _clean_text(ingestion.get("project_title"), "System")
    actors = [_item_str(a) for a in _coerce_list(ingestion.get("suggested_actors", []) or ingestion.get("target_users", []))]
    flows = [f for f in _coerce_list(ingestion.get("core_flows", [])) if isinstance(f, dict)]
    entities = [_item_str(e) for e in _coerce_list(ingestion.get("data_entities", []))]
    components = [_item_str(c) for c in _coerce_list(ingestion.get("components", []))]
    interfaces = [_item_str(i) for i in _coerce_list(ingestion.get("external_interfaces", []))]

    primary_actor = _escape_label(actors[0]) if actors else '"User"'
    secondary_actor = _escape_label(actors[1]) if len(actors) > 1 else None
    primary_id = _sanitize_id(actors[0]) if actors else "User"
    secondary_id = _sanitize_id(actors[1]) if len(actors) > 1 else None

    # ── Use Case View (flowchart with subgraph) ──
    usecase_lines = ["flowchart TD"]
    usecase_lines.append(f"  {primary_id}[{primary_actor}]")
    if secondary_id:
        usecase_lines.append(f"  {secondary_id}[{secondary_actor}]")
    usecase_lines.append(f'  subgraph System["{_escape_label(project_title)}"]')
    for i, flow in enumerate(flows[:5], start=1):
        flow_name = _clean_text(flow.get("name"), f"Workflow{i}")
        safe_fid = f"WF{i}"
        usecase_lines.append(f"    {safe_fid}[{_escape_label(flow_name)}]")
    usecase_lines.append("  end")
    if actors:
        usecase_lines.append(f"  {primary_id} --> WF1")
        if secondary_id and len(flows) > 1:
            usecase_lines.append(f"  {secondary_id} --> WF2")
    for idx, ext in enumerate(interfaces[:3], start=97):
        letter = chr(idx)
        safe_eid = f"Ext{_sanitize_id(ext)[:8]}"
        usecase_lines.append(f"  {safe_eid}[{_escape_label(ext)}]")
        usecase_lines.append(f"  System ==> {safe_eid}")
    if len(flows) > 2:
        usecase_lines.append(f"  WF1 -.->|includes| WF3")
    if len(flows) > 3:
        usecase_lines.append(f"  WF2 -.->|extends| WF4")

    # ── Class Diagram ──
    class_lines = ["classDiagram"]
    if entities:
        for entity in entities[:6]:
            safe_name = _sanitize_id(entity)
            class_lines.append(f"  class {safe_name} {{")
            class_lines.append("    +String id")
            class_lines.append("    +String status")
            class_lines.append("    +DateTime createdAt")
            class_lines.append("  }")
        for i in range(min(len(entities), 6) - 1):
            e1 = _sanitize_id(entities[i])
            e2 = _sanitize_id(entities[i + 1])
            class_lines.append(f"  {e1} \"1\" --> \"*\" {e2}")
    else:
        class_lines.append("  class System {")
        class_lines.append("    +String id")
        class_lines.append("    +String name")
        class_lines.append("    +process()")
        class_lines.append("  }")
        class_lines.append("  class Request {")
        class_lines.append("    +String id")
        class_lines.append("    +String type")
        class_lines.append("    +validate()")
        class_lines.append("  }")
        class_lines.append("  class Response {")
        class_lines.append("    +String outcome")
        class_lines.append("    +String timestamp")
        class_lines.append("  }")
        class_lines.append("  System --> Request : submits")
        class_lines.append("  Request --> Response : produces")
    comp_blocks = [c for c in components[:3] if c and c.lower() != entity.lower() for entity in (entities or [""])]
    for c in comp_blocks:
        safe_cid = _sanitize_id(c)
        class_lines.append(f"  class {safe_cid} {{")
        class_lines.append("    +handle()")
        class_lines.append("  }")
    if comp_blocks and entities:
        class_lines.append(f"  {_sanitize_id(entities[0])} --> {_sanitize_id(comp_blocks[0])} : uses")

    # ── ER Diagram ──
    er_lines = ["erDiagram"]
    if entities:
        for entity in entities[:6]:
            safe_name = _sanitize_id(entity).upper()
            er_lines.append(f"  {safe_name} {{")
            er_lines.append("    string id PK")
            er_lines.append("    string name")
            er_lines.append("    datetime created_at")
            er_lines.append("    string status")
            er_lines.append("  }")
        for i in range(min(len(entities), 6) - 1):
            e1 = _sanitize_id(entities[i]).upper()
            e2 = _sanitize_id(entities[i + 1]).upper()
            er_lines.append(f"  {e1} ||--o{{ {e2} : contains")
        if len(entities) > 2:
            e0 = _sanitize_id(entities[0]).upper()
            e2 = _sanitize_id(entities[2]).upper()
            er_lines.append(f"  {e0} ||--|| {e2} : manages")
    else:
        er_lines.append("  USER ||--o{ REQUEST : creates")
        er_lines.append("  REQUEST ||--|| RESULT : produces")
        er_lines.append("  USER {")
        er_lines.append("    string id PK")
        er_lines.append("    string email")
        er_lines.append("    datetime registered_at")
        er_lines.append("  }")
        er_lines.append("  REQUEST {")
        er_lines.append("    string id PK")
        er_lines.append("    string type")
        er_lines.append("    string status")
        er_lines.append("  }")
        er_lines.append("  RESULT {")
        er_lines.append("    string id PK")
        er_lines.append("    string outcome")
        er_lines.append("  }")

    # ── Activity / State Diagram ──
    activity_lines = ["stateDiagram-v2"]
    activity_lines.append("  [*] --> Idle")
    if flows:
        first_flow_name = _clean_text(flows[0].get("name"), "Process")
        first_flow_steps = _coerce_list(flows[0].get("steps", []))
        activity_lines.append(f"  Idle --> Started : {first_flow_name}")
        if first_flow_steps:
            prev_state = "Started"
            for step in first_flow_steps[:4]:
                safe_step = _sanitize_id(step)
                activity_lines.append(f"  {prev_state} --> {safe_step}")
                prev_state = safe_step
            activity_lines.append(f"  {prev_state} --> Completed : success")
        else:
            activity_lines.append("  Started --> Executing : proceed")
            activity_lines.append("  Executing --> Validating : data ready")
            activity_lines.append("  Validating --> Completed : success")
        activity_lines.append("  Completed --> [*]")
        activity_lines.append("  Executing --> Failed : error")
        activity_lines.append("  Failed --> Idle : retry")
    else:
        activity_lines.append("  Idle --> Processing : start")
        activity_lines.append("  Processing --> Validating")
        activity_lines.append("  Validating --> Completed : success")
        activity_lines.append("  Validating --> Failed : error")
        activity_lines.append("  Completed --> [*]")
        activity_lines.append("  Failed --> Idle : retry")

    return [
        "\n".join(usecase_lines),
        "\n".join(class_lines),
        "\n".join(er_lines),
        "\n".join(activity_lines),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: Finalization & Export
# ─────────────────────────────────────────────────────────────────────────────


async def finalize_and_export(state: SRSState) -> dict:
    """
    Assemble final SRS document and prepare for export.
    """
    sections = state.get("sections", {})
    ingestion = state.get("ingestion_summary", {})

    # Assemble final document
    final_document = assemble_document_from_sections(sections)

    try:
        from app.api.routes import _append_use_case_tables_to_document, _append_diagrams_to_document, _format_srs_document

        final_document = _append_use_case_tables_to_document(final_document, state)
        final_document = _append_diagrams_to_document(final_document, state)
        final_document = _format_srs_document(final_document, state)
    except Exception:
        final_document = final_document.strip()

    logger.info("SRS finalized; ready for export")

    export_message = (
        "**✓ SRS Document Complete!**\n\n"
        "Your Software Requirements Specification is ready."
    )

    new_messages = state.get("chat_history", []) + [AIMessage(content=export_message)]

    project_title = str(state.get("project_title", "")).strip()
    if not project_title:
        project_title = str(state.get("ingestion_summary", {}).get("project_title", "")).strip()

    return {
        "current_phase": "complete",
        "is_complete": True,
        "final_document": final_document.strip(),
        "project_title": project_title,
        "plantumul_diagrams": state.get("plantumul_diagrams", {}) or _build_plantuml_diagrams(ingestion),
        "chat_history": new_messages,
    }
