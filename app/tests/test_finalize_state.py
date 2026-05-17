from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app.graph.nodes import finalize_and_export
from app.api.routes import (
    _append_diagrams_to_document,
    _append_use_case_tables_to_document,
)
from app.formatting import assemble_document_from_sections, number_headings


@pytest.mark.asyncio
async def test_finalize_and_export_sets_completion_fields() -> None:
    state = {
        "sections": {
            "s1": "## 1. Introduction\nIntro",
            "s2": "## 2. Overall Description\nOverview",
        },
        "chat_history": [HumanMessage(content="Please finalize")],
        "project_title": "",
        "ingestion_summary": {"project_title": "FitnessStudio Manager"},
    }

    result = await finalize_and_export(state)

    assert result["current_phase"] == "complete"
    assert result["is_complete"] is True
    assert result["project_title"] == "FitnessStudio Manager"
    assert result["final_document"].startswith("# FitnessStudio Manager")
    assert "## Document Information" in result["final_document"]
    assert "## Table of Contents" in result["final_document"]
    assert "# 1 Introduction" in result["final_document"]
    assert "# 2 Overall Description" in result["final_document"]
    assert "Use Case Tables" in result["final_document"]
    assert "Diagrams" in result["final_document"]
    assert result["final_document"].strip()


def test_assemble_document_from_sections_uses_ordered_keys() -> None:
    sections = {
        "s3_nfr": "## 3.3 NFR",
        "s1": "## 1. Introduction",
        "s4": "## 4. Appendices",
    }

    doc = assemble_document_from_sections(sections)

    assert doc.startswith("## 1. Introduction")
    assert "## 3.3 NFR" in doc
    assert doc.endswith("## 4. Appendices")


def test_append_diagrams_to_document_adds_plantuml_appendix() -> None:
    document = "## 1. Introduction\nIntro"
    state_values = {
        "plantumul_diagrams": {
            "usecase": "@startuml\nAlice -> Bob\n@enduml",
        }
    }

    enriched = _append_diagrams_to_document(document, state_values)

    assert "# 6 Diagrams" in enriched
    assert "```plantuml" in enriched
    assert "@startuml" in enriched
    assert enriched.endswith("@enduml\n```") or "@enduml" in enriched


def test_append_use_case_tables_to_document_adds_catalog_and_details() -> None:
    document = "## 1. Introduction\nIntro"
    state_values = {
        "ingestion_summary": {
            "project_title": "FitnessStudio Manager",
            "suggested_actors": ["Member", "Coach"],
            "core_flows": [
                {
                    "name": "Book Class",
                    "goal": "Reserve a session",
                    "steps": ["Pick class", "Confirm booking"],
                    "success_metric": "Slot reserved",
                },
                {
                    "name": "Check In",
                    "goal": "Mark attendance",
                    "steps": ["Scan code", "Confirm arrival"],
                    "success_metric": "Attendance saved",
                },
            ],
            "components": ["Web App", "API Service"],
            "external_interfaces": ["Payment Gateway"],
            "success_criteria": ["Main booking flow works"],
        }
    }

    enriched = _append_use_case_tables_to_document(document, state_values)

    assert "# 5 Use Case Tables" in enriched
    assert "### Use Case Catalog" in enriched
    assert "| ID | Primary Actor | Use Case | Goal | Key Steps | Success Criteria |" in enriched
    assert "### UC-01 Book Class" in enriched
    assert "### UC-02 Check In" in enriched


def test_append_diagrams_to_document_falls_back_to_mermaid_blocks() -> None:
    document = "## 1. Introduction\nIntro"
    state_values = {
        "ingestion_summary": {
            "project_title": "FitnessStudio Manager",
            "core_flows": [{"name": "Class Scheduling"}, {"name": "Member Check-In"}],
            "data_entities": ["Member"],
        },
        "mermaid_blocks": [],
        "plantumul_diagrams": {},
    }

    enriched = _append_diagrams_to_document(document, state_values)

    assert "### Mermaid" in enriched
    assert "```mermaid" in enriched
    assert "flowchart TD" in enriched


def test_number_headings_deduplicates_existing_subsection_numbers() -> None:
    text = "\n".join(
        [
            "# 3 Specific Requirements",
            "## 3.2 External Interface Requirements",
            "### 3.2.1 3.2.1 User Interfaces",
        ]
    )

    numbered = number_headings(text)

    assert "### 1.1.1 User Interfaces" in numbered
    assert "3.2.1 3.2.1" not in numbered


def test_number_headings_preserves_lettered_appendices_without_numeric_prefix() -> None:
    text = "\n".join(
        [
            "# 4 Appendices",
            "## A Glossary",
            "## B Assumptions and Dependencies",
            "## C References",
            "# 5 Use Case Tables",
        ]
    )

    numbered = number_headings(text)

    assert "## A. Glossary" in numbered
    assert "## B. Assumptions and Dependencies" in numbered
    assert "## C. References" in numbered
    assert "## 4.1" not in numbered
    assert "# 2 Use Case Tables" in numbered


def test_fallback_plantuml_diagrams_produces_multiple_views() -> None:
    from app.graph.nodes import _fallback_plantuml_diagrams

    diagrams = _fallback_plantuml_diagrams(
        {
            "project_title": "FitnessStudio Manager",
            "suggested_actors": ["Member", "Coach", "Admin"],
            "components": ["Web App", "API Service", "Database"],
            "core_flows": [{"name": "Book Class", "goal": "Reserve a session"}],
            "data_entities": ["Member", "Booking"],
            "external_interfaces": ["Payment Gateway"],
        }
    )

    assert set(diagrams) == {"usecase", "component", "sequence", "activity"}
    assert "FitnessStudio Manager" in diagrams["usecase"]
    assert "Payment Gateway" in diagrams["component"]
    assert "Book Class" in diagrams["sequence"]
    assert "start" in diagrams["activity"]


def test_fallback_mermaid_diagrams_produces_richer_bundle() -> None:
    from app.api.routes import _fallback_mermaid_diagrams

    diagrams = _fallback_mermaid_diagrams(
        {
            "project_title": "FitnessStudio Manager",
            "suggested_actors": ["Member", "Coach"],
            "components": ["Web App", "API Service"],
            "core_flows": [{"name": "Book Class"}, {"name": "Check In"}],
            "data_entities": ["Member", "Booking"],
            "external_interfaces": ["Payment Gateway"],
        }
    )

    assert len(diagrams) >= 5
    assert any(block.startswith("flowchart TD") for block in diagrams)
    assert any(block.startswith("sequenceDiagram") for block in diagrams)
    assert any(block.startswith("erDiagram") for block in diagrams)
    assert any(block.startswith("classDiagram") for block in diagrams)
    assert any(block.startswith("stateDiagram-v2") for block in diagrams)
