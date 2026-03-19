"""
Unit and integration tests for the SRS Generator backend.

Run with:
    pytest app/tests/ -v

Test categories:
    - Mermaid syntax validation (validate_mermaid_syntax)
    - Requirement classification node (classify_requirements)
    - Completeness evaluation node (evaluate_completeness)
    - FastAPI route: POST /api/sessions
    - FastAPI route: GET /api/sessions/{thread_id}/document
"""

from __future__ import annotations

import base64
import json
import io
import zipfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set dummy env vars BEFORE any app module is imported at collection time.
# This prevents pydantic-settings from raising a missing-field error.
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")
os.environ.setdefault("DB_URI", "postgresql+psycopg://srs_user:srs_pass@localhost:5432/srs_db")

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def mock_app():
    """
    Create the FastAPI app with all external dependencies mocked:
    - PostgreSQL checkpointer replaced with MemorySaver
    - ChromaDB init skipped
    - LangGraph graph replaced with a mock
    """
    from langgraph.checkpoint.memory import MemorySaver

    with (
        patch("app.rag.vectorstore.init_vectorstore", return_value=None),
        patch(
            "app.db.checkpointer.managed_checkpointer",
        ) as mock_cp_ctx,
    ):
        # managed_checkpointer is an async context manager
        memory_saver = MemorySaver()
        mock_cp_ctx.return_value.__aenter__ = AsyncMock(return_value=memory_saver)
        mock_cp_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.main import create_app

        application = create_app()
        # Force-set the graph using in-memory checkpointer
        from app.graph.graph import build_graph

        application.state.graph = build_graph(checkpointer=memory_saver)
        yield application


# ════════════════════════════════════════════════════════════════════════════
# Section 1 — Mermaid Validation
# ════════════════════════════════════════════════════════════════════════════


class TestMermaidValidation:
    """Tests for app.validation.mermaid.validate_mermaid_syntax."""

    @pytest.mark.asyncio
    async def test_valid_flowchart(self):
        from app.validation.mermaid import validate_mermaid_syntax

        code = "flowchart TD\n    A[Start] --> B[End]"
        # mmdc may not be installed in CI — heuristic fallback must handle this
        valid, error = await validate_mermaid_syntax(code)
        assert valid is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_valid_sequence_diagram(self):
        from app.validation.mermaid import validate_mermaid_syntax

        code = (
            "sequenceDiagram\n"
            "    User->>API: POST /login\n"
            "    API-->>User: 200 OK"
        )
        valid, error = await validate_mermaid_syntax(code)
        assert valid is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_empty_diagram_fails(self):
        from app.validation.mermaid import validate_mermaid_syntax

        valid, error = await validate_mermaid_syntax("")
        assert valid is False
        assert error != ""

    @pytest.mark.asyncio
    async def test_unknown_diagram_type_fails(self):
        from app.validation.mermaid import validate_mermaid_syntax

        code = "invalidDiagramType\n    A --> B"
        valid, error = await validate_mermaid_syntax(code)
        assert valid is False
        assert error != ""

    @pytest.mark.asyncio
    async def test_unbalanced_brackets_fails(self):
        from app.validation.mermaid import validate_mermaid_syntax

        code = "flowchart TD\n    A[Unclosed --> B[End]"
        valid, error = await validate_mermaid_syntax(code)
        # Heuristic should detect the unclosed bracket
        assert valid is False

    @pytest.mark.asyncio
    async def test_valid_er_diagram(self):
        from app.validation.mermaid import validate_mermaid_syntax

        code = (
            'erDiagram\n'
            '    USER ||--o{ ORDER : "places"\n'
            '    ORDER ||--|{ LINE_ITEM : "contains"'
        )
        valid, error = await validate_mermaid_syntax(code)
        assert valid is True


# ════════════════════════════════════════════════════════════════════════════
# Section 2 — Requirement Classification Node
# ════════════════════════════════════════════════════════════════════════════


class TestClassifyRequirements:
    """Tests for app.graph.nodes.classify_requirements."""

    @pytest.mark.asyncio
    async def test_labels_assigned(self):
        """LLM mock returns well-formed JSON; labels should be merged into state."""
        from langchain_core.messages import AIMessage

        from app.graph.nodes import classify_requirements
        from app.graph.state import Requirement

        mock_response = AIMessage(
            content=json.dumps(
                [
                    {"id": "REQ-001", "labels": ["F"]},
                    {"id": "REQ-002", "labels": ["PE", "SC"]},
                ]
            )
        )

        state = {
            "chat_history": [],
            "document_buffer": "",
            "missing_context": [],
            "requirements": [
                Requirement(
                    id="REQ-001",
                    text="The system shall allow user registration.",
                    labels=[],
                    criteria="",
                ),
                Requirement(
                    id="REQ-002",
                    text="The API must respond within 200 ms.",
                    labels=[],
                    criteria="",
                ),
            ],
            "rag_context": "",
            "sections": {},
            "mermaid_blocks": [],
            "mermaid_errors": [],
            "mermaid_correction_attempts": 0,
            "is_complete": False,
            "qa_gaps": [],
            "final_document": "",
        }

        with patch(
            "app.graph.nodes._get_llm",
            return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
        ):
            result = await classify_requirements(state)

        reqs = result["requirements"]
        assert len(reqs) == 2
        assert reqs[0]["labels"] == ["F"]
        assert reqs[1]["labels"] == ["PE", "SC"]

    @pytest.mark.asyncio
    async def test_invalid_json_gracefully_handled(self):
        """If LLM returns garbage, existing labels should be preserved."""
        from langchain_core.messages import AIMessage

        from app.graph.nodes import classify_requirements
        from app.graph.state import Requirement

        mock_response = AIMessage(content="Sorry, I cannot classify these.")

        state: Any = {
            "chat_history": [],
            "document_buffer": "",
            "missing_context": [],
            "requirements": [
                Requirement(
                    id="REQ-001",
                    text="Some requirement.",
                    labels=["F"],
                    criteria="",
                )
            ],
            "rag_context": "",
            "sections": {},
            "mermaid_blocks": [],
            "mermaid_errors": [],
            "mermaid_correction_attempts": 0,
            "is_complete": False,
            "qa_gaps": [],
            "final_document": "",
        }

        with patch(
            "app.graph.nodes._get_llm",
            return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
        ):
            result = await classify_requirements(state)

        # Original labels should be preserved on parse failure
        assert result["requirements"][0]["labels"] == ["F"]


# ════════════════════════════════════════════════════════════════════════════
# Section 3 — Completeness Evaluation Node
# ════════════════════════════════════════════════════════════════════════════


class TestEvaluateCompleteness:
    """Tests for app.graph.nodes.evaluate_completeness."""

    @pytest.mark.asyncio
    async def test_gaps_returned(self):
        from langchain_core.messages import AIMessage

        from app.graph.nodes import evaluate_completeness

        gaps = ["What authentication mechanism will be used?", "What is the expected concurrent user count?"]
        mock_response = AIMessage(content=json.dumps({"missing": gaps}))

        state: Any = {
            "chat_history": [],
            "document_buffer": "A simple todo app.",
            "missing_context": [],
            "requirements": [],
            "rag_context": "",
            "sections": {},
            "mermaid_blocks": [],
            "mermaid_errors": [],
            "mermaid_correction_attempts": 0,
            "is_complete": False,
            "qa_gaps": [],
            "final_document": "",
        }

        with patch(
            "app.graph.nodes._get_llm",
            return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
        ):
            result = await evaluate_completeness(state)

        assert [item["question"] for item in result["missing_context"]] == gaps
        assert all(item["category"] == "General" for item in result["missing_context"])

    @pytest.mark.asyncio
    async def test_empty_gaps_means_complete(self):
        from langchain_core.messages import AIMessage

        from app.graph.nodes import evaluate_completeness

        mock_response = AIMessage(content=json.dumps({"missing": []}))

        state: Any = {
            "chat_history": [],
            "document_buffer": "Detailed specification…",
            "missing_context": [],
            "requirements": [],
            "rag_context": "",
            "sections": {},
            "mermaid_blocks": [],
            "mermaid_errors": [],
            "mermaid_correction_attempts": 0,
            "is_complete": False,
            "qa_gaps": [],
            "final_document": "",
        }

        with patch(
            "app.graph.nodes._get_llm",
            return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
        ):
            result = await evaluate_completeness(state)

        assert result["missing_context"] == []


# ════════════════════════════════════════════════════════════════════════════
# Section 3b — Mermaid Generation Resilience
# ════════════════════════════════════════════════════════════════════════════


class TestGenerateMermaid:
    """Tests for app.graph.nodes.generate_mermaid fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_diagrams_on_provider_error(self):
        from app.graph.nodes import generate_mermaid

        state: Any = {
            "chat_history": [],
            "document_buffer": "A project context for diagram generation.",
            "missing_context": [],
            "requirements": [],
            "rag_context": "",
            "sections": {},
            "mermaid_blocks": [],
            "mermaid_errors": [],
            "mermaid_correction_attempts": 0,
            "is_complete": False,
            "qa_gaps": [],
            "final_document": "",
        }

        failing_llm = MagicMock(ainvoke=AsyncMock(side_effect=RuntimeError("provider unavailable")))

        with patch("app.graph.nodes._get_llm", return_value=failing_llm):
            result = await generate_mermaid(state)

        assert len(result["mermaid_blocks"]) == 3
        assert result["mermaid_blocks"][0].startswith("flowchart TD")
        assert result["mermaid_blocks"][1].startswith("sequenceDiagram")
        assert result["mermaid_blocks"][2].startswith("erDiagram")
        assert result["mermaid_errors"] == ["", "", ""]


# ════════════════════════════════════════════════════════════════════════════
# Section 4 — API Route Tests
# ════════════════════════════════════════════════════════════════════════════


class TestSessionRoutes:
    """Tests for /api/sessions endpoints."""

    @pytest.mark.asyncio
    async def test_create_session_returns_thread_id(self, mock_app):
        async with AsyncClient(
            transport=ASGITransport(app=mock_app), base_url="http://test"
        ) as client:
            response = await client.post("/api/sessions")

        assert response.status_code == 201
        data = response.json()
        assert "thread_id" in data
        # Should be a valid UUID-like string
        assert len(data["thread_id"]) == 36

    @pytest.mark.asyncio
    async def test_create_session_unique_ids(self, mock_app):
        async with AsyncClient(
            transport=ASGITransport(app=mock_app), base_url="http://test"
        ) as client:
            r1 = await client.post("/api/sessions")
            r2 = await client.post("/api/sessions")

        assert r1.json()["thread_id"] != r2.json()["thread_id"]

    @pytest.mark.asyncio
    async def test_get_document_404_for_unknown_thread(self, mock_app):
        async with AsyncClient(
            transport=ASGITransport(app=mock_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/nonexistent-thread/document")

        # Either 404 (not found) or 202 (not complete) is acceptable
        assert response.status_code in {404, 202}

    @pytest.mark.asyncio
    async def test_health_endpoint(self, mock_app):
        async with AsyncClient(
            transport=ASGITransport(app=mock_app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestDocxExport:
    @pytest.mark.asyncio
    async def test_markdown_to_docx_bytes_applies_formatting_metadata_and_diagram_image(self):
        from app.export.docx import markdown_to_docx_bytes

        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8B6x0AAAAASUVORK5CYII="
        )

        markdown = """# Long Document Title That Should Not Be Core Metadata

This line has **bold text** and _italic text_.

```mermaid
flowchart TD
  A --> B
```
"""

        with patch("app.export.docx._render_mermaid_png", return_value=tiny_png):
            payload = markdown_to_docx_bytes(
                markdown,
                title="SRS",
                author="QA Team",
                comments="ACME Corp",
            )

        assert isinstance(payload, bytes)
        assert len(payload) > 0

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            assert "[Content_Types].xml" in names
            assert "word/document.xml" in names
            assert any(name.startswith("word/media/image") for name in names)

            document_xml = archive.read("word/document.xml").decode("utf-8")
            core_xml = archive.read("docProps/core.xml").decode("utf-8")

            assert "**bold text**" not in document_xml
            assert "bold text" in document_xml
            assert "QA Team" in core_xml
            assert "ACME Corp" in core_xml
            assert "<dc:title>SRS</dc:title>" in core_xml

    @pytest.mark.asyncio
    async def test_get_document_docx_returns_attachment(self, mock_app):
        fake_state = MagicMock(values={"final_document": "# Sample SRS\n\n## Section\nContent."})
        mock_app.state.graph.aget_state = AsyncMock(return_value=fake_state)

        async with AsyncClient(
            transport=ASGITransport(app=mock_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/test-thread/document.docx")

        assert response.status_code == 200
        assert (
            response.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment; filename=\"srs-test-thread.docx\"" in response.headers.get(
            "content-disposition", ""
        )
        assert len(response.content) > 0
