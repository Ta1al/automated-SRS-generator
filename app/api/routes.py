"""
FastAPI route handlers for the SRS generator.

Endpoints:
    POST /api/sessions
        Create a new elicitation session. Returns a unique thread_id.

    POST /api/sessions/{thread_id}/interact
        Send a user message and stream the response via Server-Sent Events.
        On the first call the graph is invoked fresh.
        On subsequent calls (after an interrupt) the graph is resumed.

    GET  /api/sessions/{thread_id}/document
        Retrieve the final assembled SRS document once the workflow completes.

    GET  /api/sessions/{thread_id}/state
        Inspect the current LangGraph state for debugging.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import logging
import re
import uuid
from typing import Any, AsyncGenerator, Literal

import httpx
import openai

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

from app.config import get_settings
from app.export.docx import markdown_to_docx_bytes
from app.formatting import assemble_document_from_sections, format_srs_body
from app.graph.prompts import GUARDRAIL_CLASSIFIER_SYSTEM, COMPLETED_GRAPH_INTENT_SYSTEM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["srs"])

# Allow fallback behavior for guardrail classifier
DISABLE_FALLBACKS = False

_guardrail_async_http_client = httpx.AsyncClient()
_guardrail_sync_http_client = httpx.Client()

SMALL_TALK_REDIRECT_MESSAGE = (
    "I am doing well, thanks. Tell me what you would like to build, and I will help "
    "you create an SRS."
)
SRS_SCOPE_REDIRECT_MESSAGE = (
    "I am here to help build Software Requirements Specification (SRS) documents. "
    "Share your product idea or requirements, and I will continue from there."
)

_DIAGRAMS_HEADER_RE = re.compile(
    r"^#{1,6}\s*(?:\d+\.?\s*)?Diagrams\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_DIAGRAM_FENCE_RE = re.compile(r"```(?:mermaid|plantuml)\b", re.IGNORECASE)

# ── Guardrail classifier ──────────────────────────────────────────────────────

def _slugify_for_filename(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *body_lines])


def _use_case_rows_from_ingestion(ingestion: dict[str, Any]) -> list[dict[str, str]]:
    actors = [str(actor).strip() for actor in (ingestion.get("suggested_actors", []) or ingestion.get("target_users", []) or ["User"]) if str(actor).strip()]
    core_flows = [flow for flow in (ingestion.get("core_flows", []) or []) if isinstance(flow, dict)]
    
    # Extract components as text, handling both strings and dicts
    components = []
    for component in (ingestion.get("components", []) or []):
        if isinstance(component, dict):
            # Extract name or description from component dict
            comp_name = str(component.get("name", "")).strip() or str(component.get("description", "")).strip()
            if comp_name:
                components.append(comp_name)
        else:
            comp_str = str(component).strip()
            if comp_str:
                components.append(comp_str)
    
    # Extract interfaces as text, handling both strings and dicts
    interfaces = []
    for interface in (ingestion.get("external_interfaces", []) or []):
        if isinstance(interface, dict):
            # Extract name or description from interface dict
            iface_name = str(interface.get("name", "")).strip() or str(interface.get("description", "")).strip()
            if iface_name:
                interfaces.append(iface_name)
        else:
            iface_str = str(interface).strip()
            if iface_str:
                interfaces.append(iface_str)

    if not core_flows:
        core_flows = [
            {
                "name": str(ingestion.get("project_purpose", "Primary workflow")).strip() or "Primary workflow",
                "goal": str(ingestion.get("project_purpose", "Deliver the product's main value")).strip() or "Deliver the product's main value",
                "steps": ["Capture user request", "Process request", "Return outcome"],
                "success_metric": str((ingestion.get("success_criteria", []) or ["User completes the main task"])[0]),
            }
        ]

    rows: list[dict[str, str]] = []
    for index, flow in enumerate(core_flows[:6], start=1):
        flow_name = str(flow.get("name", f"Use Case {index}")).strip() or f"Use Case {index}"
        goal = str(flow.get("goal", "")).strip() or str(ingestion.get("project_purpose", "")).strip() or "Deliver the requested outcome"
        steps = flow.get("steps", []) or []
        if isinstance(steps, list):
            step_text = "; ".join(str(step).strip() for step in steps[:4] if str(step).strip())
        else:
            step_text = str(steps).strip()
        if not step_text:
            step_text = "Capture request; process request; confirm outcome"
        success_metric = str(flow.get("success_metric", "")).strip() or str((ingestion.get("success_criteria", []) or ["User completes the flow"])[0]).strip()
        primary_actor = actors[(index - 1) % len(actors)] if actors else "User"
        rows.append(
            {
                "id": f"UC-{index:02d}",
                "actor": primary_actor,
                "name": flow_name,
                "goal": goal,
                "steps": step_text,
                "success": success_metric,
                "components": ", ".join(components[:3]) if components else "Application Service",
                "interfaces": ", ".join(interfaces[:3]) if interfaces else "None",
            }
        )

    return rows


def _append_use_case_tables_to_document(document_text: str, state_values: dict[str, Any]) -> str:
    """Append a use-case appendix with catalog and detail tables."""
    if "# 5 Use Case Tables" in document_text or "## 5. Use Case Tables" in document_text:
        return document_text.strip()

    ingestion = state_values.get("ingestion_summary", {}) or {}
    use_case_rows = _use_case_rows_from_ingestion(ingestion)
    if not use_case_rows:
        return document_text.strip()

    lines: list[str] = [document_text.strip(), "# 5 Use Case Tables"]

    catalog_rows = [
        [
            row["id"],
            row["actor"],
            row["name"],
            row["goal"],
            row["steps"],
            row["success"],
        ]
        for row in use_case_rows
    ]
    catalog_table = _markdown_table(
        ["ID", "Primary Actor", "Use Case", "Goal", "Key Steps", "Success Criteria"],
        catalog_rows,
    )
    if catalog_table:
        lines.append("### Use Case Catalog")
        lines.append(catalog_table)

    for row in use_case_rows[:3]:
        lines.append(f"### {row['id']} {row['name']}")
        detail_table = _markdown_table(
            ["Field", "Value"],
            [
                ["Primary Actor", row["actor"]],
                ["Goal", row["goal"]],
                ["Main Steps", row["steps"]],
                ["Success Criteria", row["success"]],
                ["Related Components", row["components"]],
                ["External Interfaces", row["interfaces"]],
            ],
        )
        if detail_table:
            lines.append(detail_table)

    return "\n\n".join(lines).strip()


def _append_diagrams_to_document(document_text: str, state_values: dict[str, Any]) -> str:
    """Append PlantUML diagrams to the end of a document body."""
    body = document_text.strip()
    if not body:
        return body

    diagrams = state_values.get("plantumul_diagrams", {}) or {}
    mermaid_blocks = state_values.get("mermaid_blocks", []) or []
    ingestion = state_values.get("ingestion_summary", {}) or {}

    if (not isinstance(diagrams, dict) or not diagrams) and not mermaid_blocks:
        mermaid_blocks = _build_mermaid_diagrams(ingestion)

    if (not isinstance(diagrams, dict) or not diagrams) and not mermaid_blocks:
        return body

    # Only skip if diagram fences appear AFTER an existing "Diagrams" heading.
    # Searching the whole body for stray fences (e.g. inside LLM-drafted sections)
    # would skip ALL state diagrams, leaving only whatever the LLM happened to embed.
    lines = body.splitlines()
    diagrams_header_idx: int | None = None
    for i, line in enumerate(lines):
        if _DIAGRAMS_HEADER_RE.match(line.strip()):
            diagrams_header_idx = i
            break
    if diagrams_header_idx is not None:
        remaining = "\n".join(lines[diagrams_header_idx:])
        if _DIAGRAM_FENCE_RE.search(remaining):
            return body

    diagram_lines: list[str] = []
    for diagram_key, diagram_code in diagrams.items():
        cleaned_key = str(diagram_key).replace("_", " ").strip().title() or "Diagram"
        cleaned_code = str(diagram_code or "").strip()
        if not cleaned_code:
            continue
        diagram_lines.append(f"### {cleaned_key}")
        diagram_lines.append("```plantuml")
        diagram_lines.append(cleaned_code)
        diagram_lines.append("```")

    if mermaid_blocks:
        diagram_lines.append("### Mermaid")
        mermaid_labels = ["Use Case Diagram", "Class Diagram", "ER Diagram", "Activity Diagram"]
        for index, mermaid_code in enumerate(mermaid_blocks, start=1):
            cleaned_code = str(mermaid_code or "").strip()
            if not cleaned_code:
                continue
            label = mermaid_labels[index - 1] if index <= len(mermaid_labels) else f"Mermaid Diagram {index}"
            diagram_lines.append(f"#### {label}")
            diagram_lines.append("```mermaid")
            diagram_lines.append(cleaned_code)
            diagram_lines.append("```")

    if not diagram_lines:
        return body

    # Reuse the header index found above (or None if no Diagrams heading existed)
    if diagrams_header_idx is None:
        return "\n\n".join([body, "# 6 Diagrams", *diagram_lines]).strip()

    insert_at = diagrams_header_idx + 1
    insertion: list[str] = []
    if insert_at < len(lines) and lines[insert_at].strip():
        insertion.append("")
    insertion.extend(diagram_lines)
    lines[insert_at:insert_at] = insertion
    return "\n".join(lines).strip()


def _format_srs_document(document_text: str, state_values: dict[str, Any]) -> str:
    """Wrap the SRS body with title metadata, a table of contents, and appendices."""
    body = str(document_text or "").strip()
    if not body:
        return ""

    if "## Table of Contents" in body:
        return body

    # Apply backend formatting (splitting and heading numbering)
    body = format_srs_body(body)

    ingestion = state_values.get("ingestion_summary", {}) or {}
    project_title = str(state_values.get("project_title") or ingestion.get("project_title") or "Software Requirements Specification").strip() or "Software Requirements Specification"
    generated_on = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    table_of_contents = _markdown_table(
        ["Section", "Title"],
        [
            ["1", "Introduction"],
            ["2", "Overall Description"],
            ["3", "Specific Requirements"],
            ["4", "Appendices"],
            ["5", "Use Case Tables"],
            ["6", "Diagrams"],
        ],
    )

    front_matter = [
        f"# {project_title}",
        "Software Requirements Specification",
        "",
        "## Document Information",
        _markdown_table(
            ["Field", "Value"],
            [
                ["Project", project_title],
                ["Generated", generated_on],
                ["Status", "Complete Draft"],
                ["Source", "Automated SRS generation"],
            ],
        ),
        "",
        "## Table of Contents",
        table_of_contents,
        "",
    ]

    return "\n\n".join(part for part in [*front_matter, body] if str(part).strip()).strip()


def _clean_text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value else fallback


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _sanitize_id(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(label)).strip("_")
    return safe or "Entity"


def _escape_label(label: str) -> str:
    l = str(label).strip()
    if not l:
        return ""
    if any(c in l for c in "\"()[]{}:;"):
        return f'"{l}"'
    return l


def _item_str(item: Any) -> str:
    if isinstance(item, dict):
        return _clean_text(item.get("name")) or _clean_text(item.get("title")) or str(item)
    return _clean_text(item, str(item))


def _build_mermaid_diagrams(ingestion: dict[str, Any]) -> list[str]:
    project_title = _clean_text(ingestion.get("project_title"), "System")
    core_flows = [f for f in _coerce_list(ingestion.get("core_flows", [])) if isinstance(f, dict)]
    data_entities = [_item_str(e) for e in _coerce_list(ingestion.get("data_entities", []))]
    components = [_item_str(c) for c in _coerce_list(ingestion.get("components", []))]
    interfaces = [_item_str(i) for i in _coerce_list(ingestion.get("external_interfaces", []))]
    actors = [_item_str(a) for a in _coerce_list(ingestion.get("suggested_actors", []) or ingestion.get("target_users", []))]
    if not actors:
        actors = ["User"]

    primary_id = _sanitize_id(actors[0])
    primary_label = _escape_label(actors[0])

    # ── Use case flowchart ──
    usecase_lines = ["flowchart TD"]
    usecase_lines.append(f"  {primary_id}[{primary_label}]")
    if len(actors) > 1:
        sid = _sanitize_id(actors[1])
        slabel = _escape_label(actors[1])
        usecase_lines.append(f"  {sid}[{slabel}]")
    usecase_lines.append(f'  subgraph System["{_escape_label(project_title)}"]')
    for i, flow in enumerate(core_flows[:5], start=1):
        fname = _clean_text(flow.get("name"), f"Flow{i}")
        usecase_lines.append(f"    WF{i}[{_escape_label(fname)}]")
    usecase_lines.append("  end")
    usecase_lines.append(f"  {primary_id} --> WF1")
    if len(actors) > 1 and len(core_flows) > 1:
        sid = _sanitize_id(actors[1])
        usecase_lines.append(f"  {sid} --> WF2")
    for idx, ext in enumerate(interfaces[:3]):
        ext_id = f"EXT{idx + 1}"
        usecase_lines.append(f"  {ext_id}[{_escape_label(ext)}]")
        usecase_lines.append(f"  System ==> {ext_id}")
    if len(core_flows) > 2:
        usecase_lines.append("  WF1 -.->|includes| WF3")

    # ── Sequence diagram ──
    primary_flow_name = _clean_text(core_flows[0].get("name"), "Primary Workflow") if core_flows else "Primary Workflow"
    seq_lines = ["sequenceDiagram"]
    seq_lines.append(f"    actor {primary_id}")
    seq_lines.append(f"    participant {_sanitize_id(project_title)}_App as {_escape_label(project_title)}")
    seq_lines.append("    participant Backend")
    seq_lines.append("    participant Store")
    seq_lines.append(f"    {primary_id}->>{_sanitize_id(project_title)}_App: Start {primary_flow_name.lower()}")
    seq_lines.append(f"    {_sanitize_id(project_title)}_App->>Backend: Submit request")
    seq_lines.append("    Backend->>Store: Validate / persist")
    seq_lines.append("    Store-->>Backend: Confirmation")
    seq_lines.append("    Backend-->>" + _sanitize_id(project_title) + "_App: Result")
    seq_lines.append("    " + _sanitize_id(project_title) + "_App-->>" + primary_id + ": Show outcome")
    if interfaces:
        seq_id = _sanitize_id(interfaces[0])
        seq_lines.append(f"    Backend->>{seq_id}: Call external service")
        seq_lines.append(f"    {seq_id}-->>Backend: Response")

    # ── ER diagram ──
    er_lines = ["erDiagram"]
    if data_entities:
        for ent in data_entities[:6]:
            safe_ent = _sanitize_id(ent).upper()
            er_lines.append(f"  {safe_ent} {{")
            er_lines.append("    string id PK")
            er_lines.append("    string name")
            er_lines.append("    datetime created_at")
            er_lines.append("    string status")
            er_lines.append("  }")
        for i in range(min(len(data_entities), 6) - 1):
            e1 = _sanitize_id(data_entities[i]).upper()
            e2 = _sanitize_id(data_entities[i + 1]).upper()
            er_lines.append(f"  {e1} ||--o{{ {e2} : contains")
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

    # ── Class diagram ──
    class_lines = ["classDiagram"]
    if data_entities:
        for ent in data_entities[:6]:
            safe_ent = _sanitize_id(ent)
            class_lines.append(f"  class {safe_ent} {{")
            class_lines.append("    +String id")
            class_lines.append("    +String status")
            class_lines.append("    +process()")
            class_lines.append("  }")
        for i in range(min(len(data_entities), 6) - 1):
            e1 = _sanitize_id(data_entities[i])
            e2 = _sanitize_id(data_entities[i + 1])
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
        class_lines.append("  }")
        class_lines.append("  System --> Request : submits")
        class_lines.append("  Request --> Response : produces")

    # ── State diagram ──
    state_lines = ["stateDiagram-v2"]
    state_lines.append("  [*] --> Idle")
    if core_flows:
        flow_name = _clean_text(core_flows[0].get("name"), "Process")
        flow_steps = _coerce_list(core_flows[0].get("steps", []))
        state_lines.append(f"  Idle --> Started : {flow_name}")
        if flow_steps:
            prev = "Started"
            for step in flow_steps[:4]:
                safe_step = _sanitize_id(step)
                state_lines.append(f"  {prev} --> {safe_step}")
                prev = safe_step
            state_lines.append(f"  {prev} --> Completed : success")
        else:
            state_lines.append("  Started --> Executing : proceed")
            state_lines.append("  Executing --> Validating : data ready")
            state_lines.append("  Validating --> Completed : success")
        state_lines.append("  Completed --> [*]")
        state_lines.append("  Executing --> Failed : error")
        state_lines.append("  Failed --> Idle : retry")
    else:
        state_lines.append("  Idle --> Processing : start")
        state_lines.append("  Processing --> Validating")
        state_lines.append("  Validating --> Completed : success")
        state_lines.append("  Validating --> Failed : error")
        state_lines.append("  Completed --> [*]")
        state_lines.append("  Failed --> Idle : retry")

    # ── Component/context view (flowchart) ──
    comp_lines = ["flowchart TD"]
    comp_lines.append(f'  C0["{_escape_label(project_title)}"]')
    if components:
        for i, comp in enumerate(components[:4], start=1):
            safe_cid = _sanitize_id(comp)
            comp_lines.append(f'  C{i}[{_escape_label(comp)}]')
        for i in range(min(len(components), 4)):
            comp_lines.append(f"  C{i} --> C{i + 1}")
    last_idx = min(len(components), 4) if components else 1
    for idx, ext in enumerate(interfaces[:2]):
        ext_id = f"EXT{idx + 1}"
        comp_lines.append(f"  {ext_id}[{_escape_label(ext)}]")
        comp_lines.append(f"  C{last_idx} ==> {ext_id}")

    # Order matches the labels in _append_diagrams_to_document:
    #   ["Use Case Diagram", "Class Diagram", "ER Diagram", "Activity Diagram"]
    return [
        "\n".join(usecase_lines),  # Use Case Diagram (flowchart TD)
        "\n".join(class_lines),    # Class Diagram (classDiagram)
        "\n".join(er_lines),       # ER Diagram (erDiagram)
        "\n".join(state_lines),    # Activity Diagram (stateDiagram-v2)
    ]


def _guardrail_ai_text(response: Any) -> str:
    if isinstance(response, AIMessage):
        return str(response.content)
    return str(response)


def _extract_json_dict(raw_text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
    if not cleaned:
        return None

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _try_parse_json_payload(raw_text: str) -> Any | None:
    """Parse a complete JSON payload from raw streamed text if possible."""
    cleaned = re.sub(r"```(?:json)?\s*", "", str(raw_text or "")).strip().rstrip("`").strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _json_to_stream_text(value: Any, depth: int = 0) -> list[str]:
    """Convert JSON payloads into readable paragraph-like lines for live streaming."""
    indent = "  " * depth

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = str(key).replace("_", " ").strip().capitalize()
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}{label}:")
                lines.extend(_json_to_stream_text(item, depth + 1))
            else:
                text = str(item).strip()
                if text:
                    lines.append(f"{indent}{label}: {text}")
        return lines

    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}-")
                lines.extend(_json_to_stream_text(item, depth + 1))
            else:
                text = str(item).strip()
                if text:
                    lines.append(f"{indent}- {text}")
        return lines

    text = str(value).strip()
    return [f"{indent}{text}"] if text else []


def _coerce_message_chunk_for_stream(
    content: Any,
    node_name: str,
    json_stream_buffers: dict[str, str],
) -> str | None:
    """
    Convert message chunks into frontend-safe text.

    - Buffers JSON fragments until valid JSON is complete, then emits readable text.
    - Suppresses incomplete JSON fragments to avoid leaking raw JSON.
    - Passes plain text through unchanged.
    """
    raw_text = str(content or "")
    if not raw_text:
        return None

    stripped = raw_text.strip()
    buffer_key = node_name or "__unknown__"
    has_buffer = buffer_key in json_stream_buffers

    starts_json_like = stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("```json")
    continue_json_like = has_buffer or starts_json_like

    if continue_json_like:
        json_stream_buffers[buffer_key] = f"{json_stream_buffers.get(buffer_key, "")}{raw_text}"
        parsed = _try_parse_json_payload(json_stream_buffers[buffer_key])
        if parsed is not None:
            lines = _json_to_stream_text(parsed)
            json_stream_buffers.pop(buffer_key, None)
            if not lines:
                return None
            rendered = "\n".join(lines).strip()
            return f"{rendered}\n" if rendered else None

        # If still incomplete JSON, wait for more chunks instead of streaming raw JSON.
        if len(json_stream_buffers[buffer_key]) > 50000:
            logger.warning("Dropping oversized JSON stream buffer from node %s", buffer_key)
            json_stream_buffers.pop(buffer_key, None)
        return None

    return raw_text


def _normalize_guardrail_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"relevant", "small_talk", "out_of_scope", "unsafe"}:
        return text
    return ""


def _redirect_message_for_label(label: str) -> str:
    if label == "small_talk":
        return SMALL_TALK_REDIRECT_MESSAGE
    if label in {"out_of_scope", "unsafe"}:
        return SRS_SCOPE_REDIRECT_MESSAGE
    return ""


def _get_guardrail_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        model=settings.guardrail_model_name,
        temperature=0.0,
        streaming=False,
        timeout=settings.guardrail_timeout_seconds,
        default_headers={
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": "SRS Generator",
        },
        http_async_client=_guardrail_async_http_client,
        http_client=_guardrail_sync_http_client,
    )


async def _invoke_guardrail_llm_with_retry(messages: list[Any], *, max_attempts: int = 2) -> Any:
    llm = _get_guardrail_llm()
    for attempt in range(1, max_attempts + 1):
        try:
            return await llm.ainvoke(messages)
        except asyncio.CancelledError:
            raise
        except (openai.APIError, httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt >= max_attempts:
                logger.warning(
                    "Guardrail LLM call failed after %d attempts: %s",
                    max_attempts,
                    exc,
                )
                raise

            backoff_seconds = float(2 ** (attempt - 1))
            logger.info(
                "Retrying guardrail LLM call (attempt %d/%d) in %.1fs after: %s",
                attempt,
                max_attempts,
                backoff_seconds,
                exc,
            )
            await asyncio.sleep(backoff_seconds)

    raise RuntimeError("Unexpected retry flow for guardrail classifier.")


async def _classify_non_resume_message_with_llm(message: str) -> tuple[bool, str, str]:
    """Classify non-resume messages via LLM; if unavailable, allow through."""
    normalized = " ".join(message.split()).strip()
    if not normalized:
        return False, SRS_SCOPE_REDIRECT_MESSAGE, "empty-message"

    try:
        response = await _invoke_guardrail_llm_with_retry(
            [
                SystemMessage(content=GUARDRAIL_CLASSIFIER_SYSTEM),
                HumanMessage(content=f"Classify this user message:\n\n{normalized}"),
            ]
        )
        payload = _extract_json_dict(_guardrail_ai_text(response))
        label = _normalize_guardrail_label(payload.get("classification") if payload else "")

        if label == "relevant":
            return True, "", "llm"

        redirect = _redirect_message_for_label(label)
        if redirect:
            return False, redirect, f"llm-{label}"

        # If guardrail returned an invalid payload, decide based on the temporary
        # DISABLE_FALLBACKS flag. When disabled, treat invalid payloads as out-of-scope
        # to avoid allowing raw JSON or unexpected outputs through to the main flow.
        if DISABLE_FALLBACKS:
            logger.info("Guardrail LLM returned invalid payload; blocking message due to DISABLE_FALLBACKS.")
            return False, SRS_SCOPE_REDIRECT_MESSAGE, "llm-fallback-disabled"
        logger.info("Guardrail LLM returned invalid classification payload; allowing message through.")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if DISABLE_FALLBACKS:
            logger.warning("Guardrail LLM classifier failed; blocking message due to DISABLE_FALLBACKS: %s", exc)
            return False, SRS_SCOPE_REDIRECT_MESSAGE, "llm-fallback-disabled"
        logger.warning("Guardrail LLM classifier failed, allowing message through: %s", exc)

    return True, "", "llm-fallback-allow"

# ── Request / Response models ─────────────────────────────────────────────────


class InteractRequest(BaseModel):
    message: str
    mode: Literal["full", "diagrams_only", "section_revision"] = "full"
    generate_diagrams: bool = False
    section_seed: dict[str, str] | None = None
    revision_mode: bool = False
    revision_target_section_key: str | None = None
    revision_target_title: str | None = None
    revision_target_content: str | None = None


# ── Helper: detect if a thread is currently interrupted ──────────────────────


async def _is_interrupted(app_state: Any, thread_id: str) -> bool:
    """Check whether the graph for ``thread_id`` is paused at an interrupt."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
        # LangGraph snapshots expose a non-empty `next` tuple when execution is
        # paused and ready to resume from an interrupt, regardless of which node
        # triggered the interruption.
        return bool(state and getattr(state, "next", None))
    except Exception:
        return False


# ── Completed-graph intent classifier ──────────────────────────────────────────

async def _classify_completed_graph_intent(
    message: str,
    existing_sections: dict[str, str],
) -> tuple[str, str]:
    """Classify a non-resume message on a completed graph into intent + target.

    Returns (intent, target_section_key).
    """
    normalized = " ".join(message.split()).strip()
    if not normalized:
        return "conversational", ""

    section_preview = "\n".join(
        f"{key}: {(content or '')[:200]}"
        for key, content in existing_sections.items()
        if content
    )[:1500]

    try:
        llm = _get_guardrail_llm()
        response = await llm.ainvoke([
            SystemMessage(content=COMPLETED_GRAPH_INTENT_SYSTEM),
            HumanMessage(
                content=f"Current SRS Preview:\n{section_preview}\n\nUser Message: {normalized}"
            ),
        ])
        payload = _extract_json_dict(_guardrail_ai_text(response))
        if payload:
            intent = str(payload.get("intent", "")).strip().lower()
            target = str(payload.get("target_section", "")).strip()
            if intent in {"revision_request", "conversational", "new_idea"}:
                return intent, target
    except Exception:
        logger.warning("Completed-graph intent classifier failed; defaulting to revision_request")

    return "revision_request", ""


async def _generate_conversational_response(
    message: str,
    existing_sections: dict[str, str],
    chat_history_summary: str,
) -> str:
    """Generate a direct conversational response without running the graph."""
    section_list = "\n".join(
        f"{key}: {(content or '')[:300]}"
        for key, content in existing_sections.items()
        if content
    )[:2000]

    prompt = f"""\
You are a helpful SRS assistant. The user has an existing SRS draft and is chatting with you.
Respond conversationally and concisely. Do NOT regenerate the SRS.

Existing sections:
{section_list}

Chat history summary:
{chat_history_summary}

User message: {message}

Respond naturally — acknowledge, answer questions about the SRS, or provide guidance.
Keep it brief (1-3 sentences)."""
    try:
        llm = _get_guardrail_llm()
        response = await llm.ainvoke([
            SystemMessage(content="You are a helpful SRS assistant. Respond concisely."),
            HumanMessage(content=prompt),
        ])
        return _guardrail_ai_text(response)
    except Exception:
        return "Got it! Let me know if you'd like to make any changes to the SRS."


# ── SSE event generator ───────────────────────────────────────────────────────

# Node display names and typical durations for better UX feedback
_NODE_DISPLAY_NAMES = {
    "ingest_and_map_domain": "Analyzing your requirements",
    "generate_elicitation_plan": "Planning elicitation questions",
    "generate_single_elicitation_question": "Asking clarifying questions",
    "classify_and_store_answers": "Processing your answer",
    "draft_from_approved_outline": "Drafting SRS sections",
    "generate_mermaid_diagrams": "Generating diagrams",
    "finalize_and_export": "Finalizing the SRS document",
    "revise_selected_section": "Revising selected section",
}

_TYPICAL_DURATION_MS = {
    "ingest_and_map_domain": 5000,
    "generate_elicitation_plan": 3000,
    "generate_single_elicitation_question": 4000,
    "classify_and_store_answers": 3000,
    "draft_from_approved_outline": 15000,
    "generate_mermaid_diagrams": 12000,
    "finalize_and_export": 3000,
    "revise_selected_section": 8000,
}

_PARALLEL_NODES: set[str] = set()

# Ordered sequence of actual graph nodes for progress tracking
_NODE_SEQUENCE_FULL_WITH_DIAGRAMS = [
    "ingest_and_map_domain",
    "generate_elicitation_plan",
    "generate_single_elicitation_question",
    "classify_and_store_answers",
    "draft_from_approved_outline",
    "generate_mermaid_diagrams",
    "finalize_and_export",
]

_NODE_SEQUENCE_FULL_NO_DIAGRAMS = [
    "ingest_and_map_domain",
    "generate_elicitation_plan",
    "generate_single_elicitation_question",
    "classify_and_store_answers",
    "draft_from_approved_outline",
    "finalize_and_export",
]

_NODE_SEQUENCE_DIAGRAMS_ONLY = _NODE_SEQUENCE_FULL_WITH_DIAGRAMS

_NODE_SEQUENCE_SECTION_REVISION = [
    "revise_selected_section",
    "finalize_and_export",
]

# Shorter sequences used when sections are pre-seeded and elicitation is skipped
_NODE_SEQUENCE_SKIP_TO_DRAFT = [
    "draft_from_approved_outline",
    "generate_mermaid_diagrams",
    "finalize_and_export",
]
_NODE_SEQUENCE_SKIP_TO_DRAFT_NO_DIAGRAMS = [
    "draft_from_approved_outline",
    "finalize_and_export",
]


def _calculate_progress(
    current_node: str,
    node_sequence: list[str],
    finished_nodes: set[str],
    started_nodes: set[str],
    parallel_nodes: set[str],
) -> dict[str, int]:
    """Calculate current step and total steps for progress display."""
    total_steps = len(node_sequence)
    current_step = 0

    for node in node_sequence:
        if node in finished_nodes:
            current_step += 1
        elif node == current_node or node in started_nodes:
            current_step += 1
            break

    return {
        "step": max(1, current_step),
        "total_steps": total_steps,
    }


def _calculate_estimated_remaining_ms(
    node_sequence: list[str],
    finished_nodes: set[str],
    parallel_nodes: set[str],
    durations_map: dict[str, int] | None = None,
) -> int:
    """Calculate estimated remaining time based on unfinished nodes."""
    remaining_ms = 0
    dm = durations_map or _TYPICAL_DURATION_MS

    for node in node_sequence:
        if node not in finished_nodes:
            remaining_ms += dm.get(node, 10000)

    return remaining_ms


async def _stream_graph(
    app_state: Any,
    thread_id: str,
    message: str,
    is_resume: bool,
    mode: Literal["full", "diagrams_only", "section_revision"],
    generate_diagrams: bool,
    section_seed: dict[str, str] | None,
    revision_mode: bool,
    revision_target_section_key: str | None,
    revision_target_title: str | None,
    revision_target_content: str | None,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that drives the LangGraph graph and yields SSE-compatible
    event dicts.

    Event types emitted:
        status   - node-level progress ({"node": "...", "status": "started"|"finished"})
        token    - streamed text chunk ({"content": "..."})
        question - HITL clarification request ({"questions": [...], "prompt": "..."})
        complete - workflow finished ({"document": "..."})
        error    - runtime error ({"message": "..."})
    """
    graph = app_state.graph
    config = {"configurable": {"thread_id": thread_id}}
    
    # Pre-fetch prior state once (used for both sequence selection and inputs)
    prior_has_all_sections = False
    prior_ingestion_summary: dict = {}
    prior_sections: dict = section_seed or {}
    prior_elicitation_answers: dict = {}
    prior_plantuml: dict = {}
    prior_mermaid: list = []
    if not is_resume:
        try:
            prior_state = await graph.aget_state(config)
            if prior_state and prior_state.values:
                pv = prior_state.values
                if pv.get("sections"):
                    prior_sections = pv.get("sections", {})
                if pv.get("ingestion_summary"):
                    prior_ingestion_summary = pv.get("ingestion_summary", {})
                if pv.get("elicitation_answers"):
                    prior_elicitation_answers = pv.get("elicitation_answers", {})
                if pv.get("plantumul_diagrams"):
                    prior_plantuml = pv.get("plantumul_diagrams", {})
                if pv.get("mermaid_blocks"):
                    prior_mermaid = pv.get("mermaid_blocks", [])
                if isinstance(prior_sections, dict):
                    prior_has_all_sections = len([k for k in ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"] if prior_sections.get(k)]) >= 6
        except Exception:
            pass
    
    # When running a full pipeline (no pre-existing sections), clear diagrams to
    # prevent stale ones from showing during elicitation.  Preserve them for
    # skip-to-draft / revision flows where they remain relevant.
    if not prior_has_all_sections:
        prior_mermaid = []
        prior_plantuml = {}

    # Determine which node sequence we're using based on mode and generate_diagrams
    if mode == "diagrams_only":
        node_sequence = _NODE_SEQUENCE_DIAGRAMS_ONLY
    elif mode == "section_revision":
        node_sequence = _NODE_SEQUENCE_SECTION_REVISION
    elif not is_resume and not revision_mode and prior_has_all_sections:
        node_sequence = _NODE_SEQUENCE_SKIP_TO_DRAFT if generate_diagrams else _NODE_SEQUENCE_SKIP_TO_DRAFT_NO_DIAGRAMS
    else:
        # For "full" mode, choose between diagrams and no-diagrams sequence
        node_sequence = _NODE_SEQUENCE_FULL_WITH_DIAGRAMS if generate_diagrams else _NODE_SEQUENCE_FULL_NO_DIAGRAMS
    
    # Track timing and progress
    import time
    node_start_times: dict[str, float] = {}
    nodes_started: set[str] = set()
    nodes_finished: set[str] = set()
    parallel_group_started = False
    stream_start_time = time.time()
    json_stream_buffers: dict[str, str] = {}

    try:
        if is_resume:
            # Resume the paused graph with the user's answer
            inputs: Any = Command(resume={"message": message})
        else:
            # Fresh invocation — preserve prior state so the graph does not
            # lose existing sections, elicitation answers, or diagrams.

            inputs = {
                "chat_history": [HumanMessage(content=message)],
                "current_phase": "ingestion",
                "pending_group_index": 0,
                "elicitation_answers": prior_elicitation_answers,
                "document_buffer": "",
                "missing_context": [],
                "ingestion_summary": prior_ingestion_summary,
                "revision_targets": [],
                "requirements": [],
                "rag_context": "",
                "sections": prior_sections,
                "plantumul_diagrams": prior_plantuml,
                "mermaid_blocks": prior_mermaid,
                "mermaid_errors": [],
                "mermaid_correction_attempts": 0,
                "generate_diagrams": generate_diagrams,
                "diagrams_only": mode == "diagrams_only",
                "revision_mode": revision_mode,
                "revision_target_section_key": revision_target_section_key or "",
                "revision_target_title": revision_target_title or "",
                "revision_target_content": revision_target_content or "",
                "revision_request": message,
                "is_complete": False,
                "qa_gaps": [],
                "major_decisions_asked": False,
                "final_document": "",
                "project_title": "",
            }

        async for stream_event in graph.astream(
            inputs,
            config=config,
            stream_mode=["updates", "messages"],
        ):
            # stream_event is a tuple: (mode, data)
            mode, data = stream_event

            if mode == "messages":
                # data = (message_chunk, metadata)
                msg_chunk, meta = data
                if hasattr(msg_chunk, "content") and msg_chunk.content:
                    node_from_meta = meta.get("langgraph_node", "") if isinstance(meta, dict) else ""
                    if node_from_meta in {
                        "draft_from_approved_outline",
                        "generate_mermaid_diagrams",
                        "finalize_and_export",
                    }:
                        continue
                    safe_content = _coerce_message_chunk_for_stream(
                        msg_chunk.content,
                        node_from_meta,
                        json_stream_buffers,
                    )
                    if safe_content:
                        yield {
                            "event": "token",
                            "data": json.dumps(
                                {
                                    "content": safe_content,
                                    "node": node_from_meta,
                                }
                            ),
                        }

            elif mode == "updates":
                # data = {node_name: {state_updates}}
                for node_name, node_updates in data.items():

                    if node_name == "__interrupt__":
                        # Graph paused - surface the questions to the client
                        if isinstance(node_updates, (list, tuple)):
                            interrupts = list(node_updates)
                        elif node_updates is None:
                            interrupts = []
                        else:
                            interrupts = [node_updates]

                        for interrupt_obj in interrupts:
                            payload = getattr(interrupt_obj, "value", None)
                            if payload is None and isinstance(interrupt_obj, dict):
                                payload = interrupt_obj.get("value", interrupt_obj)
                            if not isinstance(payload, dict):
                                payload = {}

                            event_data: dict[str, Any] = {
                                "questions": payload.get("questions", []),
                                "prompt": payload.get("prompt", ""),
                            }

                            yield {
                                "event": "question",
                                "data": json.dumps(event_data),
                            }
                        return  # Stop streaming; wait for user reply

                    if isinstance(node_updates, dict):
                        project_title = str(node_updates.get("project_title", "")).strip()
                        if project_title:
                            yield {
                                "event": "project_title",
                                "data": json.dumps({"project_title": project_title}),
                            }


                    # ── Emit node progress status with enriched timing info ──
                    current_time = time.time()
                    total_elapsed_ms = int((current_time - stream_start_time) * 1000)
                    
                    # Mark node as started if first time we see it
                    is_first_encounter = node_name not in nodes_started
                    if is_first_encounter:
                        nodes_started.add(node_name)
                        node_start_times[node_name] = current_time
                        
                        # Emit "started" event immediately for UX feedback
                        description = _NODE_DISPLAY_NAMES.get(node_name, node_name)
                        
                        # Calculate progress at node start
                        progress_info = _calculate_progress(
                            node_name,
                            node_sequence,
                            nodes_finished,
                            nodes_started,
                            _PARALLEL_NODES,
                        )

                        # Resolve durations map from app_state EMA store if available
                        durations_map = getattr(app_state, "srs_node_ema", None) or _TYPICAL_DURATION_MS

                        # Compute estimated remaining ms using current estimates
                        estimated_remaining_ms = _calculate_estimated_remaining_ms(
                            node_sequence, nodes_finished, _PARALLEL_NODES, durations_map
                        )

                        yield {
                            "event": "status",
                            "data": json.dumps(
                                {
                                    "node": node_name,
                                    "status": "started",
                                    "description": description,
                                    "step": progress_info["step"],
                                    "total_steps": progress_info["total_steps"],
                                    "elapsed_ms": total_elapsed_ms,
                                    "typical_duration_ms": int(durations_map.get(node_name, 5000)),
                                    "estimated_remaining_ms": estimated_remaining_ms,
                                }
                            ),
                        }
                    
                    # Calculate elapsed time for this node
                    node_elapsed_ms = int((current_time - node_start_times[node_name]) * 1000)
                    
                    # Get description
                    description = _NODE_DISPLAY_NAMES.get(node_name, node_name)
                    
                    # Calculate progress for finished event
                    nodes_finished.add(node_name)
                    progress_info = _calculate_progress(
                        node_name,
                        node_sequence,
                        nodes_finished,
                        nodes_started,
                        _PARALLEL_NODES,
                    )
                    
                    # Get typical duration for estimate - prefer EMA stored in app_state
                    durations_map = getattr(app_state, "srs_node_ema", None) or _TYPICAL_DURATION_MS
                    typical_ms = int(durations_map.get(node_name, 5000))

                    # Calculate estimated remaining time using EMA durations
                    estimated_remaining_ms = _calculate_estimated_remaining_ms(
                        node_sequence,
                        nodes_finished,
                        _PARALLEL_NODES,
                        durations_map,
                    )
                    
                    yield {
                        "event": "status",
                        "data": json.dumps(
                            {
                                "node": node_name,
                                "status": "finished",
                                "description": description,
                                "step": progress_info["step"],
                                "total_steps": progress_info["total_steps"],
                                "elapsed_ms": total_elapsed_ms,
                                "node_elapsed_ms": node_elapsed_ms,
                                "typical_duration_ms": typical_ms,
                                "estimated_remaining_ms": estimated_remaining_ms,
                            }
                        ),
                    }

                    # Update EMA durations in app_state for better future estimates
                    try:
                        prev_map = getattr(app_state, "srs_node_ema", None)
                        if prev_map is None:
                            prev_map = dict(_TYPICAL_DURATION_MS)
                            setattr(app_state, "srs_node_ema", prev_map)

                        alpha = 0.2
                        prev = int(prev_map.get(node_name, typical_ms))
                        observed = int(node_elapsed_ms)
                        updated = int(alpha * observed + (1 - alpha) * prev)
                        prev_map[node_name] = max(200, updated)
                    except Exception:
                        logger.exception("Failed to update EMA durations in app_state.")

                    # If the graph just finalised, emit the document
                    if node_name == "finalize_and_export":
                        final_doc = node_updates.get("final_document", "")
                        if final_doc:
                            yield {
                                "event": "complete",
                                "data": json.dumps({"document": final_doc}),
                            }
                            return

    except (openai.APIError, httpx.TransportError, httpx.TimeoutException) as exc:
        logger.exception("Network-related error during graph streaming for thread %s", thread_id)
        yield {
            "event": "error",
            "data": json.dumps({
                "message": "The AI service encountered a network error. Please retry.",
                "retryable": True,
            }),
        }
    except Exception:
        logger.exception("Non-retryable error during graph streaming for thread %s", thread_id)
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "message": "Unexpected backend error while generating the SRS. Please try again with a new session.",
                    "retryable": False,
                }
            ),
        }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/sessions", status_code=201)
async def create_session() -> JSONResponse:
    """
    Create a new SRS elicitation session.

    Returns:
        {"thread_id": "<uuid>"}
    """
    thread_id = str(uuid.uuid4())
    logger.info("New session created: %s", thread_id)
    return JSONResponse({"thread_id": thread_id}, status_code=201)


@router.post("/sessions/{thread_id}/interact")
async def interact(
    thread_id: str,
    body: InteractRequest,
    request: Request,
) -> EventSourceResponse:
    """
    Send a user message and stream the SRS generator's response.

    The first call starts the graph. Subsequent calls after an interrupt
    resume the paused graph with the user's clarification answers.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    guardrail_eligible = not body.revision_mode and body.mode != "diagrams_only"

    is_resume_task = asyncio.create_task(_is_interrupted(app_state, thread_id))
    guardrail_task: asyncio.Task[tuple[bool, str, str]] | None = None
    if guardrail_eligible:
        guardrail_task = asyncio.create_task(_classify_non_resume_message_with_llm(body.message))

    is_resume = await is_resume_task
    logger.info(
        "Interact: thread=%s resume=%s message=%.60s …",
        thread_id,
        is_resume,
        body.message,
    )

    guardrail_message = ""
    if is_resume and guardrail_task is not None and not guardrail_task.done():
        guardrail_task.cancel()
        with suppress(asyncio.CancelledError):
            await guardrail_task

    # ── Completed-graph intent detection ─────────────────────────────────────
    # If not resuming and the graph already has a completed SRS draft, classify
    # the user's intent so we can respond conversationally or route to revision
    # instead of blindly restarting the full pipeline.
    conversational_response: str | None = None
    revised_mode = body.mode
    revised_revision_mode = body.revision_mode
    revised_target_key = body.revision_target_section_key
    revised_target_title = body.revision_target_title
    revised_target_content = body.revision_target_content
    has_completed_state = False
    existing_sections: dict[str, str] = {}

    if not is_resume:
        try:
            prior_state = await app_state.graph.aget_state({"configurable": {"thread_id": thread_id}})
            if prior_state and prior_state.values:
                existing_sections = prior_state.values.get("sections", {}) or {}
                if isinstance(existing_sections, dict):
                    section_keys = list(existing_sections.keys())
                    has_completed_state = len([k for k in ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"] if existing_sections.get(k)]) >= 6
        except Exception:
            pass

        if has_completed_state:
            intent, target = await _classify_completed_graph_intent(body.message, existing_sections)

            if intent == "conversational":
                past_msgs = ""
                try:
                    from langchain_core.messages import BaseMessage
                    prior_state = await app_state.graph.aget_state({"configurable": {"thread_id": thread_id}})
                    if prior_state and prior_state.values:
                        hist = prior_state.values.get("chat_history", [])
                        if isinstance(hist, list):
                            past_msgs = "\n".join(
                                f"{m.__class__.__name__}: {m.content[:200]}"
                                for m in hist[-6:]
                                if isinstance(m, BaseMessage)
                            )
                except Exception:
                    pass
                conversational_response = await _generate_conversational_response(
                    body.message, existing_sections, past_msgs,
                )
                logger.info(
                    "Interact conversational response for thread=%s intent=%s",
                    thread_id, intent,
                )

            elif intent == "revision_request" and target in existing_sections:
                revised_mode = "section_revision"
                revised_revision_mode = True
                revised_target_key = target
                revised_target_content = existing_sections[target]
                _section_titles = {
                    "s1": "Section 1 · Introduction",
                    "s2": "Section 2 · Overall Description",
                    "s3_functional": "Section 3.1 · Functional Requirements",
                    "s3_external": "Section 3.2 · External Interface Requirements",
                    "s3_nfr": "Section 3.3 · Non-Functional Requirements",
                    "s4": "Section 4 · Appendices",
                }
                revised_target_title = _section_titles.get(target, target)
                logger.info(
                    "Interact auto-revision for thread=%s target=%s",
                    thread_id, target,
                )

    if not is_resume and guardrail_task is not None:
        is_relevant, redirect_message, classifier_source = await guardrail_task
        if not is_relevant:
            guardrail_message = redirect_message
            logger.info(
                "Interact guardrail redirect: thread=%s mode=%s source=%s",
                thread_id,
                body.mode,
                classifier_source,
            )

    async def event_generator() -> AsyncGenerator[dict, None]:
        if await request.is_disconnected():
            return

        if guardrail_message:
            yield {
                "event": "token",
                "data": json.dumps({"content": guardrail_message, "node": "message_guard"}),
            }
            return

        if conversational_response:
            yield {
                "event": "token",
                "data": json.dumps({"content": conversational_response, "node": "message_guard"}),
            }
            return

        async for event in _stream_graph(
            app_state,
            thread_id,
            body.message,
            is_resume,
            revised_mode,
            body.generate_diagrams,
            body.section_seed,
            revised_revision_mode,
            revised_target_key,
            revised_target_title,
            revised_target_content,
        ):
            if await request.is_disconnected():
                logger.info("Client disconnected mid-stream for thread %s", thread_id)
                break
            yield event

    return EventSourceResponse(event_generator(), ping=15)


@router.delete("/sessions/{thread_id}", status_code=204)
async def delete_session(thread_id: str, request: Request) -> None:
    """
    Delete all persisted LangGraph checkpoint state for a thread.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    checkpointer = getattr(app_state.graph, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=501, detail="Session deletion is not supported.")

    delete_thread = getattr(checkpointer, "adelete_thread", None)
    if not callable(delete_thread):
        raise HTTPException(status_code=501, detail="Session deletion is not supported.")

    try:
        await delete_thread(thread_id)
        logger.info("Deleted backend session state for thread %s", thread_id)
    except Exception as exc:
        logger.exception("Failed to delete backend session state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete session state.") from exc


@router.get("/sessions/{thread_id}/document")
async def get_document(thread_id: str, request: Request) -> JSONResponse:
    """
    Return the final SRS Markdown document for a completed session.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {exc}") from exc

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Session not found.")

    final_doc = state.values.get("final_document", "")
    if not final_doc and state.values.get("current_phase") == "complete":
        final_doc = assemble_document_from_sections(state.values.get("sections", {}))
    final_doc = _append_use_case_tables_to_document(final_doc, state.values)
    final_doc = _append_diagrams_to_document(final_doc, state.values)
    final_doc = _format_srs_document(final_doc, state.values)
    if not final_doc:
        raise HTTPException(
            status_code=202,
            detail="Document not yet complete. Continue the elicitation session.",
        )

    return JSONResponse({"thread_id": thread_id, "document": final_doc})


@router.get("/sessions/{thread_id}/document.docx")
async def get_document_docx(thread_id: str, request: Request) -> Response:
    """
    Return the final SRS document as a DOCX file.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {exc}") from exc

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Session not found.")

    final_doc = state.values.get("final_document", "")
    if not final_doc:
        final_doc = assemble_document_from_sections(state.values.get("sections", {}))
    final_doc = _append_use_case_tables_to_document(final_doc, state.values)
    final_doc = _append_diagrams_to_document(final_doc, state.values)
    final_doc = _format_srs_document(final_doc, state.values)
    if not final_doc:
        # Provide more helpful error message based on generation state
        missing_context = state.values.get("missing_context", [])
        qa_gaps = state.values.get("qa_gaps", [])
        if missing_context or qa_gaps:
            detail = "Document still being refined. Please answer the remaining clarification questions to finalize the SRS."
        else:
            detail = "Document not yet complete. Please wait for the generation process to finish or continue the elicitation session."
        raise HTTPException(
            status_code=202,
            detail=detail,
        )

    settings = get_settings()
    ingestion = state.values.get("ingestion_summary", {}) or {}
    project_title = str(
        state.values.get("project_title", "")
        or ingestion.get("project_title", "")
    ).strip()
    resolved_title = project_title or settings.docx_title
    download_name = (
        f"{_slugify_for_filename(project_title)}.docx"
        if project_title
        else f"srs-{thread_id}.docx"
    )

    docx_bytes = markdown_to_docx_bytes(
        final_doc,
        title=resolved_title,
        author=settings.docx_author,
        comments=settings.docx_comment,
    )
    
    if not docx_bytes:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate DOCX file. The document content may be corrupted.",
        )
    
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
        },
    )


@router.get("/sessions/{thread_id}/document.md")
async def get_document_markdown(thread_id: str, request: Request) -> Response:
    """Return the final SRS document as a Markdown file."""
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {exc}") from exc

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Session not found.")

    final_doc = state.values.get("final_document", "")
    if not final_doc and state.values.get("current_phase") == "complete":
        final_doc = assemble_document_from_sections(state.values.get("sections", {}))
    final_doc = _append_use_case_tables_to_document(final_doc, state.values)
    final_doc = _append_diagrams_to_document(final_doc, state.values)
    final_doc = _format_srs_document(final_doc, state.values)
    if not final_doc:
        missing_context = state.values.get("missing_context", [])
        qa_gaps = state.values.get("qa_gaps", [])
        if missing_context or qa_gaps:
            detail = "Document still being refined. Please answer the remaining clarification questions to finalize the SRS."
        else:
            detail = "Document not yet complete. Please wait for the generation process to finish or continue the elicitation session."
        raise HTTPException(status_code=202, detail=detail)

    settings = get_settings()
    ingestion = state.values.get("ingestion_summary", {}) or {}
    project_title = str(
        state.values.get("project_title", "")
        or ingestion.get("project_title", "")
    ).strip()
    resolved_title = project_title or settings.docx_title
    download_name = (
        f"{_slugify_for_filename(project_title)}.md"
        if project_title
        else f"srs-{thread_id}.md"
    )

    return Response(
        content=final_doc,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Document-Title": resolved_title,
        },
    )


@router.get("/sessions/{thread_id}/state")
async def get_state(thread_id: str, request: Request) -> JSONResponse:
    """
    Debug endpoint - return the raw LangGraph state snapshot.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return JSONResponse(
        {
            "thread_id": thread_id,
            "next": list(state.next) if state.next else [],
            "is_complete": bool(
                state.values.get("is_complete", False)
                or state.values.get("current_phase", "") == "complete"
            ),
            "current_phase": state.values.get("current_phase", ""),
            "pending_group_index": state.values.get("pending_group_index", 0),
            "missing_context_count": len(state.values.get("missing_context", [])),
            "requirements_count": len(state.values.get("requirements", [])),
            "sections_drafted": list(state.values.get("sections", {}).keys()),
            "mermaid_blocks_count": len(state.values.get("mermaid_blocks", [])),
            "missing_context": state.values.get("missing_context", []),
            "qa_gaps": state.values.get("qa_gaps", []),
            "sections": state.values.get("sections", {}),
            "section_structures": state.values.get("section_structures", {}),
            "plantumul_diagrams": state.values.get("plantumul_diagrams", {}),
            "mermaid_blocks": state.values.get("mermaid_blocks", []),
            "ingestion_summary": state.values.get("ingestion_summary", {}),
            "revision_targets": state.values.get("revision_targets", []),
            "project_title": state.values.get("project_title", ""),
            "final_document": state.values.get("final_document", ""),
        }
    )
