"""
LangGraph node functions for the SRS generator workflow.

Each node accepts the full ``SRSState`` and returns a partial dict that
LangGraph merges back into the shared state via the declared reducers.

Convention:
    async def node_name(state: SRSState) -> dict
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from app.config import get_settings
from app.graph import prompts
from app.graph.state import ClarificationQuestion, Requirement, SRSState
from app.rag.vectorstore import retrieve
from app.validation.mermaid import validate_mermaid_syntax

logger = logging.getLogger(__name__)

# ── LLM factory ───────────────────────────────────────────────────────────────


def _get_llm(temperature: float = 0.2, streaming: bool = True) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointed at OpenRouter."""
    settings = get_settings()
    return ChatOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        model=settings.model_name,
        temperature=temperature,
        streaming=streaming,
        default_headers={
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": "SRS Generator",
        },
    )


# ── Helper: extract text from last AI response ────────────────────────────────


def _ai_text(response: Any) -> str:
    if isinstance(response, AIMessage):
        return str(response.content)
    return str(response)


def _parse_json(text: str) -> Any:
    """Extract the first JSON object or array from a string."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    return json.loads(text)


def _normalize_questions(raw_questions: Any) -> list[ClarificationQuestion]:
    """Normalize evaluator and QA gap output to a structured question shape."""
    normalized: list[ClarificationQuestion] = []

    if not isinstance(raw_questions, list):
        return normalized

    for item in raw_questions:
        if isinstance(item, str):
            question = item.strip()
            if question:
                normalized.append(
                    ClarificationQuestion(
                        category="General",
                        question=question,
                        suggested_options=[],
                        rationale="This detail is required to complete the specification.",
                    )
                )
            continue

        if not isinstance(item, dict):
            continue

        question = str(item.get("question", "")).strip()
        if not question:
            continue

        suggested_options = item.get("suggested_options", [])
        if not isinstance(suggested_options, list):
            suggested_options = []

        normalized.append(
            ClarificationQuestion(
                category=str(item.get("category", "General")).strip() or "General",
                question=question,
                suggested_options=[str(option).strip() for option in suggested_options if str(option).strip()],
                rationale=str(item.get("rationale", "")).strip()
                or "This detail is required to complete the specification.",
            )
        )

    return normalized


# ── Node 1: Retrieve RAG context ──────────────────────────────────────────────


async def retrieve_rag_context(state: SRSState) -> dict:
    """Query ChromaDB with the latest user message to surface regulatory context."""
    messages = state.get("chat_history", [])
    query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            query = str(msg.content)
            break

    if not query:
        return {"rag_context": ""}

    context = retrieve(query, n_results=5)
    logger.debug("RAG retrieved %d chars for query: %.80s …", len(context), query)
    return {"rag_context": context}


# ── Node 2: Elicit requirements ───────────────────────────────────────────────


async def elicit_requirements(state: SRSState) -> dict:
    """Parse user input and produce a preliminary structured outline."""
    llm = _get_llm(temperature=0.1)

    context_block = ""
    if state.get("rag_context"):
        context_block = (
            "\n\nRELEVANT REGULATORY / STANDARDS CONTEXT:\n" + state["rag_context"]
        )

    messages = [
        SystemMessage(content=prompts.ELICITOR_SYSTEM),
        *state.get("chat_history", []),
    ]
    if context_block:
        messages.append(HumanMessage(content=context_block))

    response = await llm.ainvoke(messages)
    raw = _ai_text(response)

    # Try to parse as JSON; fall back to storing as-is
    try:
        parsed = _parse_json(raw)
        buffer = json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, ValueError):
        buffer = raw

    return {
        "document_buffer": buffer,
        "chat_history": [AIMessage(content=f"Elicitation result:\n{buffer}")],
    }


# ── Node 3: Evaluate completeness ─────────────────────────────────────────────


async def evaluate_completeness(state: SRSState) -> dict:
    """Identify missing information gaps using structured evaluation."""
    llm = _get_llm(temperature=0.0)

    context_summary = state.get("document_buffer", "(no data yet)")
    qa_gaps = state.get("qa_gaps", [])
    extra = ""
    if qa_gaps:
        extra = "\n\nADDITIONAL GAPS IDENTIFIED BY QA REVIEWER:\n" + "\n".join(
            f"- {g}" for g in qa_gaps
        )

    user_prompt = (
        f"Current extracted context:\n{context_summary}"
        f"\n\nConversation history covers {len(state.get('chat_history', []))} messages."
        f"{extra}"
        "\n\nIdentify ALL remaining gaps."
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.EVALUATOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ]
    )

    try:
        data = _parse_json(_ai_text(response))
        missing = _normalize_questions(data.get("missing", []))
    except (json.JSONDecodeError, ValueError, AttributeError):
        logger.warning("Evaluator returned non-JSON; treating as complete.")
        missing = []

    logger.info("Evaluator found %d gaps.", len(missing))
    return {"missing_context": missing, "qa_gaps": []}


# ── Node 4: Ask clarifying questions (HITL interrupt) ─────────────────────────


async def ask_clarifying_questions(state: SRSState) -> dict:
    """
    Pause graph execution and surface clarifying questions to the user.

    LangGraph's ``interrupt()`` serialises the current state to PostgreSQL and
    yields control back to the FastAPI SSE stream.  Execution resumes when the
    user provides answers via ``Command(resume=...)``.
    """
    missing = state.get("missing_context", [])
    qa_gaps = state.get("qa_gaps", [])

    combined_questions: list[ClarificationQuestion] = []
    seen_questions: set[str] = set()
    for item in [*missing, *qa_gaps]:
        question_text = str(item.get("question", "")).strip()
        if not question_text or question_text in seen_questions:
            continue
        seen_questions.add(question_text)
        combined_questions.append(item)

    if not combined_questions:
        return {}

    question_blocks: list[str] = []
    for index, item in enumerate(combined_questions, start=1):
        question_lines = [f"{index}. [{item.get('category', 'General')}] {item.get('question', '')}"]
        options = item.get("suggested_options", [])
        if options:
            question_lines.append("   Suggested options:")
            question_lines.extend(f"   - {option}" for option in options)
        rationale = item.get("rationale", "")
        if rationale:
            question_lines.append(f"   Why this matters: {rationale}")
        question_blocks.append("\n".join(question_lines))

    formatted_questions = "\n\n".join(question_blocks)
    prompt_text = (
        "I drafted an initial SRS using the best available information. "
        "To improve and complete it, I need a few more details:\n\n"
        + formatted_questions
    )

    # interrupt() raises GraphInterrupt internally — LangGraph catches it,
    # saves state, and routes the payload back through the SSE stream.
    human_answer: dict = interrupt(
        {
            "type": "clarification_needed",
            "questions": combined_questions,
            "prompt": prompt_text,
        }
    )

    # Merge the user's answer back into chat history
    answer_text = human_answer.get("message", "") if isinstance(human_answer, dict) else str(human_answer)
    return {
        "chat_history": [HumanMessage(content=answer_text)],
        "document_buffer": state.get("document_buffer", "")
        + f"\n\n--- USER CLARIFICATION ---\n{answer_text}",
        "qa_gaps": [],
    }


# ── Node 5: Classify requirements ─────────────────────────────────────────────


async def classify_requirements(state: SRSState) -> dict:
    """Assign 12-label taxonomy tags to every extracted requirement."""
    llm = _get_llm(temperature=0.0)

    # Build a stub requirement list from document_buffer if none exist yet
    existing: list[Requirement] = state.get("requirements", [])
    if not existing:
        # Auto-generate stubs from document_buffer
        buffer = state.get("document_buffer", "")
        lines = [
            ln.strip()
            for ln in buffer.splitlines()
            if ln.strip() and len(ln.strip()) > 20
        ]
        existing = [
            Requirement(id=f"REQ-{i + 1:03d}", text=ln, labels=[], criteria="")
            for i, ln in enumerate(lines[:50])  # cap at 50
        ]

    if not existing:
        return {"requirements": []}

    batch = [{"id": r["id"], "text": r["text"]} for r in existing]
    user_prompt = f"Classify these requirements:\n{json.dumps(batch, indent=2)}"

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.CLASSIFIER_SYSTEM),
            HumanMessage(content=user_prompt),
        ]
    )

    try:
        classifications: list[dict] = _parse_json(_ai_text(response))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Classifier returned non-JSON; skipping label assignment.")
        return {"requirements": existing}

    # Build lookup map
    label_map: dict[str, list[str]] = {
        item["id"]: item["labels"] for item in classifications if "id" in item
    }

    updated: list[Requirement] = []
    for req in existing:
        updated.append(
            Requirement(
                id=req["id"],
                text=req["text"],
                labels=label_map.get(req["id"], req.get("labels", [])),
                criteria=req.get("criteria", ""),
            )
        )

    return {"requirements": updated}


# ── Node 6: Draft Section 1 ───────────────────────────────────────────────────


async def draft_section_1(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.3)
    context = _build_writing_context(state)

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S1_SYSTEM),
            HumanMessage(content=context),
        ]
    )
    return {"sections": {"s1": _ai_text(response)}}


# ── Node 7: Draft Section 2 ───────────────────────────────────────────────────


async def draft_section_2(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.3)
    context = _build_writing_context(state)

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S2_SYSTEM),
            HumanMessage(content=context),
        ]
    )
    return {"sections": {"s2": _ai_text(response)}}


# ── Node 8a: Draft Section 3 — Functional Requirements ───────────────────────


async def draft_section_3_fr(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S3_FR_SYSTEM),
            HumanMessage(content=context),
        ]
    )
    return {"sections": {"s3_fr": _ai_text(response)}}


# ── Node 8b: Draft Section 3 — Non-Functional Requirements ───────────────────


async def draft_section_3_nfr(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    # Inject RAG context into NFR writing for regulatory grounding
    rag = state.get("rag_context", "")
    extra = f"\n\nREGULATORY CONTEXT (use to generate L-NNN, SE-NNN requirements):\n{rag}" if rag else ""

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S3_NFR_SYSTEM),
            HumanMessage(content=context + extra),
        ]
    )
    return {"sections": {"s3_nfr": _ai_text(response)}}


# ── Node 8c: Draft Section 3 — External Interfaces ───────────────────────────


async def draft_section_3_iface(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S3_IFACE_SYSTEM),
            HumanMessage(content=context),
        ]
    )
    return {"sections": {"s3_iface": _ai_text(response)}}


# ── Node 9: Draft Section 4 — Verification Matrix ────────────────────────────


async def draft_section_4(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.1)
    sections = state.get("sections", {})

    section_3_combined = "\n\n".join(
        [
            sections.get("s3_iface", ""),
            sections.get("s3_fr", ""),
            sections.get("s3_nfr", ""),
        ]
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.WRITER_S4_SYSTEM),
            HumanMessage(
                content=f"Generate the verification matrix for:\n\n{section_3_combined}"
            ),
        ]
    )
    return {"sections": {"s4": _ai_text(response)}}


# ── Node 10: Generate Mermaid diagrams ────────────────────────────────────────


async def generate_mermaid(state: SRSState) -> dict:
    """Generate three Mermaid diagrams: architecture, sequence, ER."""
    llm = _get_llm(temperature=0.1)
    context = _build_writing_context(state)

    diagram_configs = [
        (
            "a high-level system architecture (flowchart TD) diagram",
            prompts.MERMAID_ARCHITECTURE_PROMPT,
        ),
        (
            "a sequence diagram for the primary user workflow",
            prompts.MERMAID_SEQUENCE_PROMPT,
        ),
        (
            "an entity-relationship diagram for core data entities",
            prompts.MERMAID_ER_PROMPT,
        ),
    ]

    blocks: list[str] = []
    for idx, (diagram_label, diagram_prompt) in enumerate(diagram_configs):
        system_prompt = prompts.MERMAID_SYSTEM.format(diagram_type=diagram_label)
        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content=f"System context:\n{context}\n\nGenerate: {diagram_prompt}"
                    ),
                ]
            )
            raw = _ai_text(response)
            # Strip markdown fences to get raw diagram code
            code = _extract_mermaid_code(raw)
        except Exception as exc:
            logger.exception(
                "Mermaid generation failed for '%s'; using fallback diagram.",
                diagram_label,
            )
            code = _fallback_mermaid_code(idx)
        blocks.append(code)

    return {
        "mermaid_blocks": blocks,
        "mermaid_errors": [""] * len(blocks),
        "mermaid_correction_attempts": 0,
    }


# ── Node 11: Validate Mermaid syntax ─────────────────────────────────────────


async def validate_mermaid(state: SRSState) -> dict:
    """Run mmdc (or heuristic fallback) on each generated diagram block."""
    blocks = state.get("mermaid_blocks", [])
    errors: list[str] = []

    for block in blocks:
        valid, error_msg = await validate_mermaid_syntax(block)
        errors.append("" if valid else error_msg)

    failed = sum(1 for e in errors if e)
    logger.info("Mermaid validation: %d/%d diagrams valid.", len(blocks) - failed, len(blocks))
    return {"mermaid_errors": errors}


# ── Node 12: Correct Mermaid syntax ──────────────────────────────────────────


async def correct_mermaid(state: SRSState) -> dict:
    """Request LLM to fix each diagram that failed validation."""
    llm = _get_llm(temperature=0.0)
    blocks = list(state.get("mermaid_blocks", []))
    errors = state.get("mermaid_errors", [])
    attempts = state.get("mermaid_correction_attempts", 0)

    for i, (block, error) in enumerate(zip(blocks, errors)):
        if not error:
            continue  # Already valid

        correction_prompt = prompts.CORRECTOR_SYSTEM.format(
            original_code=f"```mermaid\n{block}\n```",
            error_message=error,
        )
        response = await llm.ainvoke(
            [HumanMessage(content=correction_prompt)]
        )
        corrected = _extract_mermaid_code(_ai_text(response))
        if corrected:
            blocks[i] = corrected

    return {
        "mermaid_blocks": blocks,
        "mermaid_correction_attempts": attempts + 1,
    }


# ── Node 13: QA Review ───────────────────────────────────────────────────────


async def qa_review(state: SRSState) -> dict:
    """LLM-as-a-Judge pass over the assembled draft document."""
    llm = _get_llm(temperature=0.0)

    sections = state.get("sections", {})
    draft = "\n\n".join(
        [
            sections.get("s1", ""),
            sections.get("s2", ""),
            sections.get("s3_iface", ""),
            sections.get("s3_fr", ""),
            sections.get("s3_nfr", ""),
            sections.get("s4", ""),
        ]
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompts.QA_REVIEWER_SYSTEM),
            HumanMessage(content=f"Review this SRS draft:\n\n{draft[:12000]}"),
        ]
    )

    try:
        data = _parse_json(_ai_text(response))
        passed: bool = bool(data.get("passed", False))
        gaps = _normalize_questions(data.get("gaps", []))
    except (json.JSONDecodeError, ValueError):
        logger.warning("QA reviewer returned non-JSON; defaulting to passed=True.")
        passed = True
        gaps = []

    logger.info("QA review: passed=%s, gaps=%d", passed, len(gaps))
    return {"is_complete": passed, "qa_gaps": gaps}


# ── Node 14: Finalize document ────────────────────────────────────────────────


async def finalize_document(state: SRSState) -> dict:
    """Assemble all validated sections and Mermaid diagrams into final Markdown."""
    sections = state.get("sections", {})
    blocks = state.get("mermaid_blocks", [])
    errors = state.get("mermaid_errors", [])

    diagram_titles = [
        "System Architecture Diagram",
        "Primary User Workflow — Sequence Diagram",
        "Core Data Model — Entity Relationship Diagram",
    ]

    diagrams_md = ""
    for title, block, error in zip(diagram_titles, blocks, errors):
        if error:
            diagrams_md += f"\n\n> ⚠️ *{title} could not be validated and has been omitted.*\n"
        else:
            diagrams_md += f"\n\n### {title}\n\n```mermaid\n{block}\n```\n"

    final = "\n\n".join(
        filter(
            None,
            [
                sections.get("s1", ""),
                sections.get("s2", ""),
                "## 3. Requirements",
                sections.get("s3_iface", ""),
                sections.get("s3_fr", ""),
                sections.get("s3_nfr", ""),
                sections.get("s4", ""),
                "## Appendix A — System Diagrams" + diagrams_md if diagrams_md.strip() else "",
            ],
        )
    )

    logger.info("Final document assembled: %d characters.", len(final))
    return {"final_document": final}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_writing_context(state: SRSState) -> str:
    """Build a concise context string for writer node prompts."""
    parts: list[str] = []

    buffer = state.get("document_buffer", "")
    if buffer:
        parts.append(f"## ELICITATION OUTLINE\n{buffer[:3000]}")

    history = state.get("chat_history", [])
    if history:
        convo = "\n".join(
            f"{'USER' if isinstance(m, HumanMessage) else 'AI'}: {str(m.content)[:400]}"
            for m in history[-10:]  # last 10 messages
        )
        parts.append(f"## CONVERSATION CONTEXT (last 10 messages)\n{convo}")

    reqs = state.get("requirements", [])
    if reqs:
        req_lines = "\n".join(
            f"- [{r['id']}] ({', '.join(r['labels'] or ['?'])}): {r['text'][:200]}"
            for r in reqs[:30]
        )
        parts.append(f"## CLASSIFIED REQUIREMENTS\n{req_lines}")

    pending_questions = state.get("missing_context", [])
    if pending_questions:
        question_lines = "\n".join(
            f"- [{item.get('category', 'General')}] {item.get('question', '')}"
            for item in pending_questions
            if item.get("question")
        )
        if question_lines:
            parts.append(
                "## OPEN CLARIFICATIONS\n"
                "Draft the strongest best-effort SRS you can, and make any uncertainty explicit as an assumption instead of omitting the requirement area.\n"
                f"{question_lines}"
            )

    return "\n\n".join(parts) or "No context available yet."


def _extract_mermaid_code(text: str) -> str:
    """Extract raw Mermaid code from a fenced code block."""
    match = re.search(r"```(?:mermaid)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no fence, return stripped text as-is (might be raw code)
    return text.strip()


def _fallback_mermaid_code(index: int) -> str:
    """Return a minimal valid Mermaid diagram when LLM generation fails."""
    if index == 0:
        return "\n".join(
            [
                "flowchart TD",
                "    User[User] --> API[API Layer]",
                "    API --> Core[Core Services]",
                "    Core --> DB[(Database)]",
            ]
        )

    if index == 1:
        return "\n".join(
            [
                "sequenceDiagram",
                "    participant User",
                "    participant System",
                "    User->>System: Submit request",
                "    System-->>User: Return response",
            ]
        )

    return "\n".join(
        [
            "erDiagram",
            "    USER ||--o{ REQUIREMENT : creates",
            "    REQUIREMENT {",
            "        string id",
            "        string title",
            "    }",
        ]
    )
