"""
LangGraph node functions for the SRS generator workflow.

Each node accepts the full ``SRSState`` and returns a partial dict that
LangGraph merges back into the shared state via the declared reducers.

Convention:
    async def node_name(state: SRSState) -> dict
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from typing import Any

import httpx
import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from app.config import get_settings
from app.graph import prompts
from app.graph.state import ClarificationQuestion, Requirement, SRSState
from app.rag.mermaid_syntax import retrieve_mermaid_syntax
from app.rag.vectorstore import retrieve
from app.validation.mermaid import validate_mermaid_syntax

logger = logging.getLogger(__name__)

# ── Shared HTTP clients ────────────────────────────────────────────────────────
# langchain_openai's internal _cached_async_httpx_client uses @lru_cache keyed
# only by (base_url, timeout), ignoring event-loop identity.  When a cached
# AsyncClient is reused across different event loops the connections from the
# old (now-closed) loop cause "RuntimeError: Event loop is closed", which the
# openai SDK re-raises as "APIError: Network connection lost".
# Passing explicit clients here bypasses that cache entirely.
# See: https://github.com/langchain-ai/langchain/issues/35783
_async_http_client = httpx.AsyncClient()
_sync_http_client = httpx.Client()

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
        timeout=45,  # fail fast on stalled requests; retry loop handles recovery
        default_headers={
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": "SRS Generator",
        },
        http_async_client=_async_http_client,
        http_client=_sync_http_client,
    )


async def _llm_invoke_with_retry(
    llm: ChatOpenAI,
    messages: list[Any],
    *,
    node_name: str,
    max_attempts: int = 3,
) -> Any:
    """Invoke the LLM with bounded retries for transient transport/API failures."""
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await llm.ainvoke(messages)
        except (openai.APIError, httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt >= max_attempts:
                logger.exception(
                    "LLM call failed after %d attempts in node '%s'.",
                    max_attempts,
                    node_name,
                )
                raise

            backoff_seconds = float(2 ** (attempt - 1))
            logger.warning(
                "Transient LLM error in node '%s' (attempt %d/%d): %s. Retrying in %.1fs.",
                node_name,
                attempt,
                max_attempts,
                exc,
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected retry state in _llm_invoke_with_retry.")


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


_HIGH_IMPACT_CATEGORIES = {
    "technology",
    "tech stack",
    "stack",
    "architecture",
    "deployment",
    "hosting",
    "infrastructure",
    "authentication",
    "authorization",
    "identity",
    "security",
    "privacy",
    "compliance",
    "legal",
    "data",
    "integrations",
    "integration",
    "scalability",
    "performance",
    "availability",
    "sla",
}

_HIGH_IMPACT_KEYWORDS = (
    "auth",
    "oauth",
    "sso",
    "saml",
    "rbac",
    "deployment",
    "hosting",
    "cloud",
    "on-prem",
    "serverless",
    "database",
    "residency",
    "pii",
    "gdpr",
    "hipaa",
    "pci",
    "integration",
    "payment",
    "throughput",
    "latency",
    "scal",
    "concurrent",
    "user count",
    "capacity",
    "load",
    "availability",
    "uptime",
    "region",
)


def _is_high_impact_question(item: ClarificationQuestion) -> bool:
    category = str(item.get("category", "")).strip().lower()
    question = str(item.get("question", "")).strip().lower()
    rationale = str(item.get("rationale", "")).strip().lower()

    if category in _HIGH_IMPACT_CATEGORIES:
        return True

    haystack = f"{question} {rationale}"
    return any(keyword in haystack for keyword in _HIGH_IMPACT_KEYWORDS)


def _filter_major_questions(questions: list[ClarificationQuestion]) -> list[ClarificationQuestion]:
    """Keep only high-impact clarification questions that materially affect architecture."""
    return [item for item in questions if _is_high_impact_question(item)]


def _normalize_project_title(value: Any) -> str:
    """Normalize a candidate project title into a concise single-line string."""
    if not isinstance(value, str):
        return ""

    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return ""
    return normalized[:120]


def _extract_project_title(parsed_payload: Any) -> str:
    """Read project title from elicitor JSON payload with reasonable fallbacks."""
    if not isinstance(parsed_payload, dict):
        return ""

    direct_title = _normalize_project_title(parsed_payload.get("project_title"))
    if direct_title:
        return direct_title

    preliminary = parsed_payload.get("preliminary_sections")
    if isinstance(preliminary, dict):
        nested_title = _normalize_project_title(preliminary.get("product_name"))
        if nested_title:
            return nested_title

    return ""


def _tokenize_for_overlap(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _retrieve_draft_context(
    sections: dict[str, str],
    *,
    target_key: str,
    query: str,
    top_k: int = 3,
) -> str:
    """Retrieve top-k relevant snippets from existing draft sections using lexical overlap."""
    query_tokens = _tokenize_for_overlap(query)
    if not query_tokens:
        return ""

    query_counts = Counter(query_tokens)
    scored_chunks: list[tuple[float, str, str]] = []

    for section_key, section_content in sections.items():
        if section_key == target_key:
            continue
        text = str(section_content or "").strip()
        if not text:
            continue

        chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
        if not chunks:
            chunks = [text]

        for chunk in chunks:
            chunk_tokens = _tokenize_for_overlap(chunk)
            if not chunk_tokens:
                continue
            chunk_counts = Counter(chunk_tokens)
            overlap = sum(min(query_counts[token], chunk_counts[token]) for token in query_counts)
            if overlap <= 0:
                continue

            score = overlap / max(8, len(chunk_tokens))
            scored_chunks.append((score, section_key, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    top = scored_chunks[:top_k]
    if not top:
        return ""

    return "\n\n".join(
        f"[From {section_key}]\n{chunk[:1400]}" for _, section_key, chunk in top
    )


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

    response = await _llm_invoke_with_retry(llm, messages, node_name="elicit_requirements")
    raw = _ai_text(response)
    project_title = state.get("project_title", "")

    # Try to parse as JSON; fall back to storing as-is
    try:
        parsed = _parse_json(raw)
        buffer = json.dumps(parsed, indent=2)
        extracted_title = _extract_project_title(parsed)
        if extracted_title:
            project_title = extracted_title
    except (json.JSONDecodeError, ValueError):
        buffer = raw

    return {
        "document_buffer": buffer,
        "project_title": project_title,
        "chat_history": [AIMessage(content=f"Elicitation result:\n{buffer}")],
    }


# ── Node 3: Evaluate completeness ─────────────────────────────────────────────


async def evaluate_completeness(state: SRSState) -> dict:
    """Identify unresolved major decisions after the initial draft is produced."""
    if state.get("major_decisions_asked", False):
        return {"missing_context": [], "qa_gaps": []}

    llm = _get_llm(temperature=0.0)

    sections = state.get("sections", {})
    current_draft = "\n\n".join(
        filter(
            None,
            [
                sections.get("s1", ""),
                sections.get("s2", ""),
                sections.get("s3_iface", ""),
                sections.get("s3_fr", ""),
                sections.get("s3_nfr", ""),
                sections.get("s4", ""),
            ],
        )
    ).strip()

    if not current_draft:
        current_draft = state.get("document_buffer", "(no draft yet)")

    user_prompt = (
        "Current SRS draft (may be partial):\n"
        f"{current_draft[:14000]}"
        f"\n\nConversation history covers {len(state.get('chat_history', []))} messages."
        "\n\nIdentify only high-impact unanswered decisions using the required JSON format."
    )

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.EVALUATOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ],
        node_name="evaluate_completeness",
    )

    try:
        data = _parse_json(_ai_text(response))
        missing = _normalize_questions(data.get("missing", []))
        missing = _filter_major_questions(missing)
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

    prompt_text = (
        "I drafted an initial SRS using the best available information. "
        "Please answer the clarification form so I can finalize it accurately."
    )

    # interrupt() raises GraphInterrupt internally — LangGraph catches it,
    # saves state, and routes the payload back through the SSE stream.
    payload = {
        "type": "clarification_needed",
        "questions": combined_questions,
        "prompt": prompt_text,
    }
    human_answer: dict = interrupt(payload)

    # Require a non-empty clarification response before resuming workflow.
    # This prevents downstream steps (including diagram generation) from
    # running while major decision gaps are still unanswered.
    answer_text = human_answer.get("message", "") if isinstance(human_answer, dict) else str(human_answer)
    while not str(answer_text).strip():
        reprompt = (
            "Please answer the clarification questions before I continue with "
            "the draft and diagram generation."
        )
        human_answer = interrupt(
            {
                "type": "clarification_needed",
                "questions": combined_questions,
                "prompt": reprompt,
            }
        )
        answer_text = human_answer.get("message", "") if isinstance(human_answer, dict) else str(human_answer)

    answer_text = str(answer_text).strip()

    # Merge the user's answer back into chat history
    return {
        "chat_history": [HumanMessage(content=answer_text)],
        "document_buffer": state.get("document_buffer", "")
        + f"\n\n--- USER CLARIFICATION ---\n{answer_text}",
        "qa_gaps": [],
        "major_decisions_asked": True,
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

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.CLASSIFIER_SYSTEM),
            HumanMessage(content=user_prompt),
        ],
        node_name="classify_requirements",
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

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S1_SYSTEM),
            HumanMessage(content=context),
        ],
        node_name="draft_section_1",
    )
    raw_section = _ai_text(response)
    completed_section = _ensure_section_1_completeness(raw_section, state)
    return {"sections": {"s1": completed_section}}


# ── Node 7: Draft Section 2 ───────────────────────────────────────────────────


async def draft_section_2(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.3)
    context = _build_writing_context(state)

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S2_SYSTEM),
            HumanMessage(content=context),
        ],
        node_name="draft_section_2",
    )
    return {"sections": {"s2": _ai_text(response)}}


# ── Node 8a: Draft Section 3 — Functional Requirements ───────────────────────


async def draft_section_3_fr(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S3_FR_SYSTEM),
            HumanMessage(content=context),
        ],
        node_name="draft_section_3_fr",
    )
    return {"sections": {"s3_fr": _ai_text(response)}}


# ── Node 8b: Draft Section 3 — Non-Functional Requirements ───────────────────


async def draft_section_3_nfr(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    # Inject RAG context into NFR writing for regulatory grounding
    rag = state.get("rag_context", "")
    extra = f"\n\nREGULATORY CONTEXT (use to generate L-NNN, SE-NNN requirements):\n{rag}" if rag else ""

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S3_NFR_SYSTEM),
            HumanMessage(content=context + extra),
        ],
        node_name="draft_section_3_nfr",
    )
    return {"sections": {"s3_nfr": _ai_text(response)}}


# ── Node 8c: Draft Section 3 — External Interfaces ───────────────────────────


async def draft_section_3_iface(state: SRSState) -> dict:
    llm = _get_llm(temperature=0.2)
    context = _build_writing_context(state)

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S3_IFACE_SYSTEM),
            HumanMessage(content=context),
        ],
        node_name="draft_section_3_iface",
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

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.WRITER_S4_SYSTEM),
            HumanMessage(
                content=f"Generate the verification matrix for:\n\n{section_3_combined}"
            ),
        ],
        node_name="draft_section_4",
    )
    return {"sections": {"s4": _ai_text(response)}}


async def revise_selected_section(state: SRSState) -> dict:
    """Revise only the selected section using context retrieved from the existing draft."""
    sections = dict(state.get("sections", {}))
    target_key = str(state.get("revision_target_section_key", "")).strip()
    if not target_key:
        return {"sections": {}}

    current_text = str(state.get("revision_target_content", "")).strip() or str(
        sections.get(target_key, "")
    ).strip()
    if not current_text:
        return {"sections": {}}

    requested_change = str(state.get("revision_request", "")).strip()
    target_title = str(state.get("revision_target_title", "")).strip() or target_key

    retrieval_query = "\n".join(
        filter(None, [target_title, target_key, requested_change, current_text[:900]])
    )
    draft_context = _retrieve_draft_context(
        sections,
        target_key=target_key,
        query=retrieval_query,
        top_k=4,
    )

    llm = _get_llm(temperature=0.2)
    prompt_parts = [
        f"Selected section title: {target_title}",
        f"Selected section key: {target_key}",
        "Current section markdown:",
        current_text,
        "User requested change:",
        requested_change or "(No additional instruction provided)",
    ]

    if draft_context:
        prompt_parts.extend(
            [
                "Retrieved context from other draft sections:",
                draft_context,
            ]
        )

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.REVISE_SECTION_SYSTEM),
            HumanMessage(content="\n\n".join(prompt_parts)),
        ],
        node_name="revise_selected_section",
    )
    revised_section = _ai_text(response).strip() or current_text

    return {"sections": {target_key: revised_section}}


# ── Node 10: Generate Mermaid diagrams ────────────────────────────────────────


async def generate_mermaid(state: SRSState) -> dict:
    """Generate three Mermaid diagrams: architecture, sequence, ER."""
    llm = _get_llm(temperature=0.1)
    context = _build_writing_context(state)

    diagram_configs = [
        (
            "flowchart",
            "a high-level system architecture (flowchart TD) diagram",
            prompts.MERMAID_ARCHITECTURE_PROMPT,
        ),
        (
            "sequence",
            "a sequence diagram for the primary user workflow",
            prompts.MERMAID_SEQUENCE_PROMPT,
        ),
        (
            "er",
            "an entity-relationship diagram for core data entities",
            prompts.MERMAID_ER_PROMPT,
        ),
    ]

    async def _generate_one(
        index: int,
        diagram_kind: str,
        diagram_label: str,
        diagram_prompt: str,
    ) -> str:
        system_prompt = prompts.MERMAID_SYSTEM.format(diagram_type=diagram_label)
        syntax_context = retrieve_mermaid_syntax(
            diagram_type=diagram_kind,
            query=f"{context}\n{diagram_prompt}",
            top_k=3,
        )
        user_content = [f"System context:\n{context}"]
        if syntax_context:
            user_content.append(
                "Mermaid syntax reference (follow strictly):\n"
                f"{syntax_context}"
            )
        user_content.append(f"Generate: {diagram_prompt}")

        response = await _llm_invoke_with_retry(
            llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content="\n\n".join(user_content)),
            ],
            node_name="generate_mermaid",
        )
        raw = _ai_text(response)
        code = _extract_mermaid_code(raw)
        return code or _fallback_mermaid_code(index)

    generation_tasks = [
        _generate_one(idx, diagram_kind, diagram_label, diagram_prompt)
        for idx, (diagram_kind, diagram_label, diagram_prompt) in enumerate(diagram_configs)
    ]
    generation_results = await asyncio.gather(*generation_tasks, return_exceptions=True)

    blocks: list[str] = []
    for idx, result in enumerate(generation_results):
        if isinstance(result, Exception):
            logger.exception(
                "Mermaid generation failed for diagram index %d; using fallback.",
                idx,
                exc_info=result,
            )
            blocks.append(_fallback_mermaid_code(idx))
            continue
        blocks.append(result)

    return {
        "mermaid_blocks": blocks,
        "mermaid_errors": [""] * len(blocks),
        "mermaid_correction_attempts": 0,
    }


# ── Node 11: Validate Mermaid syntax ─────────────────────────────────────────


async def validate_mermaid(state: SRSState) -> dict:
    """Run mmdc (or heuristic fallback) on each generated diagram block."""
    blocks = state.get("mermaid_blocks", [])
    validation_tasks = [validate_mermaid_syntax(block) for block in blocks]
    validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

    errors: list[str] = []
    for result in validation_results:
        if isinstance(result, Exception):
            logger.exception("Unexpected Mermaid validation error.", exc_info=result)
            errors.append("Unexpected Mermaid validator failure.")
            continue

        valid, error_msg = result
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

    async def _correct_one(index: int, block: str, error: str) -> tuple[int, str | None]:
        correction_prompt = prompts.CORRECTOR_SYSTEM.format(
            original_code=f"```mermaid\n{block}\n```",
            error_message=error,
        )
        response = await _llm_invoke_with_retry(
            llm,
            [HumanMessage(content=correction_prompt)],
            node_name="correct_mermaid",
        )
        corrected = _extract_mermaid_code(_ai_text(response))
        return index, corrected or None

    correction_tasks = [
        _correct_one(i, block, error)
        for i, (block, error) in enumerate(zip(blocks, errors))
        if error
    ]

    if correction_tasks:
        correction_results = await asyncio.gather(*correction_tasks, return_exceptions=True)
        for result in correction_results:
            if isinstance(result, Exception):
                logger.exception("Mermaid correction task failed.", exc_info=result)
                continue

            index, corrected = result
            if corrected:
                blocks[index] = corrected

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

    response = await _llm_invoke_with_retry(
        llm,
        [
            SystemMessage(content=prompts.QA_REVIEWER_SYSTEM),
            HumanMessage(content=f"Review this SRS draft:\n\n{draft[:12000]}"),
        ],
        node_name="qa_review",
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


_SECTION_1_REQUIRED_HEADINGS = [
    "## 1. Introduction",
    "### 1.1 Purpose",
    "### 1.2 Scope",
    "### 1.3 Definitions, Acronyms, and Abbreviations",
    "### 1.4 References",
    "### 1.5 Overview",
]


def _normalize_heading_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


_SECTION_1_TITLE_TO_HEADING = {
    _normalize_heading_title(heading.split(" ", 1)[1]): heading
    for heading in _SECTION_1_REQUIRED_HEADINGS
}


def _unwrap_markdown_fence(markdown: str) -> str:
    stripped = str(markdown or "").strip()
    fence_match = re.match(
        r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$",
        stripped,
        flags=re.IGNORECASE,
    )
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _has_meaningful_markdown_body(lines: list[str]) -> bool:
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue

        if re.match(r"^\s{0,3}[-*_]{3,}\s*$", trimmed):
            continue

        if re.match(r"^#{1,6}\s*$", trimmed):
            continue

        if re.match(r"^#{1,6}\s+", trimmed):
            continue

        normalized = re.sub(r"[`*_~|>#-]", " ", trimmed)
        if re.search(r"[A-Za-z0-9]", normalized):
            return True

    return False


def _resolve_project_name(state: SRSState) -> str:
    explicit_title = _normalize_project_title(state.get("project_title", ""))
    if explicit_title:
        return explicit_title

    for message in state.get("chat_history", []):
        if not isinstance(message, HumanMessage):
            continue

        text = re.sub(r"\s+", " ", str(message.content or "")).strip()
        if not text:
            continue

        text = re.sub(
            r"^i\s+want\s+to\s+(?:build|make|create)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = text.strip(" .")
        if text:
            return text[:80]

    return "the system"


def _section_1_fallback_content(state: SRSState) -> dict[str, list[str]]:
    project_name = _resolve_project_name(state)
    references = [
        "- IEEE Std 830-1998: IEEE Recommended Practice for Software Requirements Specifications.",
        "- ISO/IEC/IEEE 29148: Systems and software engineering - Life cycle processes - Requirements engineering.",
        "- Project elicitation notes and stakeholder clarification responses captured in this session.",
    ]

    return {
        "## 1. Introduction": [
            (
                f"This Software Requirements Specification (SRS) defines the functional, interface, "
                f"quality, and verification requirements for {project_name}. "
                "It serves as the contractual baseline for implementation, validation, and acceptance."
            ),
        ],
        "### 1.1 Purpose": [
            (
                f"The purpose of this SRS is to specify verifiable requirements for {project_name} "
                "so that engineering, QA, and stakeholders can implement and validate a consistent solution."
            ),
        ],
        "### 1.2 Scope": [
            (
                f"The scope includes browser-based gameplay behavior, input handling, obstacle interaction, "
                f"scoring logic, and performance expectations for {project_name}."
            ),
            "Out-of-scope features include unrelated platform expansion unless explicitly requested in later revisions.",
        ],
        "### 1.3 Definitions, Acronyms, and Abbreviations": [
            "| Term | Definition |",
            "| --- | --- |",
            f"| {project_name} | Target software product defined by this SRS. |",
            "| Player | End user interacting with gameplay controls. |",
            "| Game loop | Continuous update and render cycle executed during runtime. |",
            "| Obstacle | Dynamic object that the player must avoid or navigate. |",
        ],
        "### 1.4 References": references,
        "### 1.5 Overview": [
            (
                "Section 2 describes the product context and constraints, Section 3 captures detailed functional "
                "and quality requirements, and Section 4 defines the verification approach for acceptance."
            ),
        ],
    }


def _collect_section_1_blocks(markdown: str) -> dict[str, list[str]]:
    blocks = {heading: [] for heading in _SECTION_1_REQUIRED_HEADINGS}
    lines = markdown.splitlines()

    current_heading: str | None = None
    current_level: int | None = None

    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)

        if heading_match:
            level = len(heading_match.group(1))
            title_key = _normalize_heading_title(heading_match.group(2))
            mapped_heading = _SECTION_1_TITLE_TO_HEADING.get(title_key)

            if current_heading is not None and current_level is not None and level <= current_level:
                current_heading = None
                current_level = None

            if mapped_heading:
                current_heading = mapped_heading
                current_level = level
                continue

        if current_heading is not None:
            blocks[current_heading].append(line)

    return blocks


def _ensure_section_1_completeness(markdown: str, state: SRSState) -> str:
    source = _unwrap_markdown_fence(markdown).replace("\r\n", "\n").replace("\r", "\n")
    existing_blocks = _collect_section_1_blocks(source)
    fallback_blocks = _section_1_fallback_content(state)

    missing_or_empty: list[str] = []
    result_lines: list[str] = []

    for heading in _SECTION_1_REQUIRED_HEADINGS:
        result_lines.append(heading)

        body_lines = [line.rstrip() for line in existing_blocks.get(heading, [])]
        if _has_meaningful_markdown_body(body_lines):
            # Trim leading/trailing blank lines while preserving internal formatting.
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            result_lines.extend(body_lines)
        else:
            missing_or_empty.append(heading)
            result_lines.extend(fallback_blocks[heading])

        result_lines.append("")

    if missing_or_empty:
        logger.info(
            "Section 1 fallback content inserted for headings: %s",
            ", ".join(missing_or_empty),
        )

    return "\n".join(result_lines).strip()


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
