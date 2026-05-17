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
from app.graph import prompts
from app.graph.state import SRSState, IngestionSummary, OutlineItem, ClarificationQuestion
from app.rag.vectorstore import retrieve

logger = logging.getLogger(__name__)

settings = get_settings()

OUTLINE_APPROVE_COMMAND = "[[approve_outline]]"
FINALIZE_COMMAND = "[[finalize_srs]]"
REQUEST_REVIEW_EDIT_COMMAND = "[[request_review_edit]]"


def _latest_human_message(state: SRSState) -> HumanMessage | None:
    for message in reversed(state.get("chat_history", [])):
        if isinstance(message, HumanMessage):
            return message
    return None


def _normalize_message_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _is_control_command(message_text: str, command: str) -> bool:
    return _normalize_message_text(message_text) == command


def _assemble_document_from_sections(sections: dict[str, str] | None) -> str:
    ordered_keys = ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"]
    parts = [str((sections or {}).get(key, "")).strip() for key in ordered_keys if str((sections or {}).get(key, "")).strip()]
    return "\n\n".join(parts).strip()


def _fallback_plantuml_diagrams(ingestion: dict[str, Any]) -> dict[str, str]:
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


class CoreFlowModel(BaseModel):
    """A single core flow."""
    name: str = Field(..., description="Flow name")
    goal: str = Field(..., description="Flow goal or outcome")
    steps: list[str] = Field(..., description="Ordered steps of the flow")
    success_metric: str = Field(..., description="How success is measured")


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


class OutlineItemModel(BaseModel):
    """A proposed SRS outline section."""
    section_id: str = Field(..., description="Section identifier (e.g., 1, 2.1, 3.2)")
    title: str = Field(..., description="Section title")
    description: str = Field(..., description="What goes in this section")
    included: bool = Field(default=True, description="Should this section be included?")
    rationale: str = Field(..., description="Why include or exclude")
    subsection_suggestions: list[str] = Field(default_factory=list, description="Suggested subsections")
    user_notes: str = Field(default="", description="User feedback")


class OutlineListModel(BaseModel):
    """List of outline items."""
    outline_items: list[OutlineItemModel] = Field(..., description="All outline sections")


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
        final_document = _assemble_document_from_sections(sections)
        return {
            "current_phase": "complete",
            "is_complete": True,
            "final_document": final_document,
            "project_title": str(ingestion.get("project_title", "")).strip(),
            "plantumul_diagrams": _fallback_plantuml_diagrams(ingestion),
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

    group_titles = [
        "User Roles & Flows",
        "Functional Boundaries",
        "Non-Functional Requirements",
        "Edge Cases & Risk Mitigation"
    ]

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
        confirmation += " Now let me generate an outline for your SRS."

    new_messages = state.get("chat_history", []) + [AIMessage(content=confirmation)]

    return {
        "elicitation_answers": elicitation_answers,
        "chat_history": new_messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Outline Review
# ─────────────────────────────────────────────────────────────────────────────


async def generate_outline(state: SRSState) -> dict:
    """
    Generate IEEE 830 outline from ingestion and elicitation data.
    Uses structured output to ensure OutlineListModel is returned.
    """
    ingestion = state.get("ingestion_summary", {})
    elicitation = state.get("elicitation_answers", {})

    logger.info("Generating SRS outline")

    system_prompt = prompts.OUTLINE_GENERATOR_SYSTEM.format(
        user_context="Generating outline for project",
        ingestion_summary=json.dumps(ingestion, indent=2),
        elicitation_answers=json.dumps(elicitation, indent=2),
    )

    response = await _llm_invoke_structured(
        system_prompt=system_prompt,
        output_model=OutlineListModel,  # Outline can include full IEEE 830 structure
    )

    outline_data = response.outline_items

    confirmation = (
        "**✓ Proposed SRS Outline Generated**\n\n"
        "Please review the outline in the right panel. You can:\n"
        "- Ask me to include/exclude any section\n"
        "- Request changes to rationales\n"
        "- Suggest subsection adjustments\n\n"
        "When ready, use the Approve outline button to start drafting."
    )

    new_messages = state.get("chat_history", []) + [AIMessage(content=confirmation)]

    # Convert models to dicts for state storage
    outline_items_dicts = [item.model_dump(mode="json") for item in outline_data]

    return {
        "outline_items": outline_items_dicts,
        "chat_history": new_messages,
    }


async def wait_for_outline_approval(state: SRSState) -> dict:
    """
    Interrupt node: Wait for user to approve or modify outline.
    """
    outline_items = state.get("outline_items", [])
    human_answer = interrupt(
        {
            "type": "outline_review",
            "prompt": "Review the outline and use the Approve outline button when ready.",
            "outline": outline_items,
        }
    )

    if isinstance(human_answer, dict):
        user_feedback = _normalize_message_text(str(human_answer.get("message", "")))
    else:
        user_feedback = _normalize_message_text(str(human_answer or ""))

    # Check if user approved
    if _is_control_command(user_feedback, OUTLINE_APPROVE_COMMAND) or any(
        keyword in user_feedback
        for keyword in ["looks good", "approved", "proceed", "ready", "draft", "okay"]
    ):
        logger.info("Outline approved by user")
        confirmation = "✓ Outline approved. I am now drafting your SRS sections."
        new_messages = state.get("chat_history", []) + [
            HumanMessage(content=str(human_answer.get("message", "")) if isinstance(human_answer, dict) else str(human_answer or "")),
            AIMessage(content=confirmation),
        ]
        return {
            "outline_approved": True,
            "chat_history": new_messages,
        }
    else:
        # User wants modifications; acknowledge and re-interrupt
        logger.info("Outline changes requested; re-interrupting")
        acknowledgment = (
            "I've noted your feedback. Update the outline details in chat, then click Approve outline "
            "when you are ready to move to drafting."
        )
        new_messages = state.get("chat_history", []) + [
            HumanMessage(content=str(human_answer.get("message", "")) if isinstance(human_answer, dict) else str(human_answer or "")),
            AIMessage(content=acknowledgment),
        ]

        return {"outline_approved": False, "chat_history": new_messages}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Drafting
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

    # Run all 6 drafters in parallel
    async def draft_section(section_key: str, prompt_template: str) -> tuple[str, str]:
        prompt = prompt_template.format(**context)
        response = await _llm_invoke_text(system_prompt=prompt, temperature=0.6)
        return section_key, response

    drafters = [
        ("s1", prompts.DRAFT_SECTION_1_SYSTEM),
        ("s2", prompts.DRAFT_SECTION_2_SYSTEM),
        ("s3_functional", prompts.DRAFT_SECTION_3_FUNCTIONAL_SYSTEM),
        ("s3_external", prompts.DRAFT_SECTION_3_EXTERNAL_SYSTEM),
        ("s3_nfr", prompts.DRAFT_SECTION_3_NFR_SYSTEM),
        ("s4", prompts.DRAFT_SECTION_4_SYSTEM),
    ]

    results = await asyncio.gather(*[draft_section(key, prompt) for key, prompt in drafters])

    sections = {key: content for key, content in results}

    # Normalize section headings: strip numeric/Section prefixes while preserving IDs like [F-123]
    def _normalize_title_text(title: str) -> str:
        t = title or ""
        t = t.strip()
        # Remove leading 'Section' or numeric prefixes like '3.1', 'Section 3.1 -', etc.
        t = re.sub(r'^(Section\s+)?[0-9]+(?:\.[0-9]+)*\s*[-:\.]?\s*', '', t, flags=re.I)
        # Collapse whitespace
        t = " ".join(t.split())
        return t

    def _normalize_section_content(content: str) -> str:
        if not content:
            return content
        lines = content.splitlines()
        out_lines: list[str] = []
        for line in lines:
            # Normalize markdown headings: '# Title'
            m = re.match(r'^(#{1,6}\s*)(.+)$', line)
            if m:
                prefix = m.group(1)
                title = m.group(2)
                out_lines.append(f"{prefix}{_normalize_title_text(title)}")
                continue

            # Handle plain numeric heading lines like '3.3 Performance Requirements'
            m2 = re.match(r'^\s*([0-9]+(?:\.[0-9]+)*)\s*[-:\.]?\s*(.+)$', line)
            if m2 and len(line.strip()) < 120 and (line.strip().count(' ') < 10):
                # Convert to a level-2 markdown heading with cleaned title
                title = m2.group(2)
                out_lines.append(f"## {_normalize_title_text(title)}")
                continue

            out_lines.append(line)

        return "\n".join(out_lines)

    sections = {k: _normalize_section_content(v) for k, v in sections.items()}

    logger.info(f"Completed drafting all sections")

    return {
        "sections": sections,
        "current_phase": "review_refine",
    }


async def present_draft_for_review(state: SRSState) -> dict:
    """
    Format completed sections into a readable SRS document and present for review.
    """
    sections = state.get("sections", {})

    # Assemble document
    document = ""
    for key in ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"]:
        if key in sections:
            document += sections[key] + "\n\n"

    # Emit as message
    review_message = (
        "**✓ SRS Draft Complete!**\n\n" + document + "\n\n"
        "Please review the draft. You can:\n"
        "- Request section regeneration (e.g., 'Regenerate section 3.1')\n"
        "- Request inline edits (e.g., 'In section 1.2, change X to Y')\n"
        "- Ask clarifying questions\n\n"
        "When satisfied, use the Finalize button to complete the document."
    )

    new_messages = state.get("chat_history", []) + [AIMessage(content=review_message)]

    logger.info("Draft presented for review; awaiting feedback")

    # Present the draft; the feedback node will handle the interrupt/resume.
    pass

    return {
        "chat_history": new_messages,
    }


async def process_review_feedback(state: SRSState) -> dict:
    """
    Parse user feedback and route to regeneration or finalization.
    """
    sections = state.get("sections", {})
    human_answer = interrupt(
        {
            "type": "draft_review",
            "prompt": "Review the draft and use the Finalize document button when ready.",
            "sections": sections,
        }
    )

    if isinstance(human_answer, dict):
        user_feedback = _normalize_message_text(str(human_answer.get("message", "")))
    else:
        user_feedback = _normalize_message_text(str(human_answer or ""))

    # Check if user wants to finalize
    if _is_control_command(user_feedback, FINALIZE_COMMAND) or any(
        keyword in user_feedback for keyword in ["finalize", "done", "looks good", "ready", "complete"]
    ):
        logger.info("User approved final draft; proceeding to finalization")
        return {
            "revision_targets": [],
        }

    # Check if regeneration requested
    if _is_control_command(user_feedback, REQUEST_REVIEW_EDIT_COMMAND) or any(
        word in user_feedback for word in ["regenerate", "rewrite", "redo"]
    ):
        logger.info("Regeneration requested")
        return {
            "revision_targets": ["s1"],  # Placeholder; would parse section numbers
        }

    # Otherwise, acknowledge and re-interrupt
    acknowledgment = "I'll make those changes. One moment..."
    new_messages = state.get("chat_history", []) + [
        HumanMessage(content=str(human_answer.get("message", "")) if isinstance(human_answer, dict) else str(human_answer or "")),
        AIMessage(content=acknowledgment),
    ]

    return {
        "chat_history": new_messages,
    }


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
    final_document = _assemble_document_from_sections(sections)

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
        "plantumul_diagrams": state.get("plantumul_diagrams", {}) or _fallback_plantuml_diagrams(ingestion),
        "chat_history": new_messages,
    }
