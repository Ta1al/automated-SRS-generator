# Use Case Diagram

## High-Level System Use Cases

```mermaid
graph TD
    User((Stakeholder)) --> UC1[Create New SRS]
    User --> UC2[Answer Clarifying Questions]
    User --> UC3[Approve Outline]
    User --> UC4[Review Draft]
    User --> UC5[Request Section Revision]
    User --> UC6[Finalize Document]
    User --> UC7[Export SRS]

    UC1 --> UC1_1[Submit Product Idea]
    UC1 --> UC1_2[Review Ingested Summary]

    UC2 --> UC2_1[Provide User Roles & Flows]
    UC2 --> UC2_2[Define Functional Boundaries]
    UC2 --> UC2_3[Specify NFRs]
    UC2 --> UC2_4[Identify Edge Cases]

    UC4 --> UC4_1[Request Inline Edits]
    UC4 --> UC4_2[Request Section Regeneration]

    UC7 --> UC7_1[Download Markdown JSON]
    UC7 --> UC7_2[Download Markdown File]
    UC7 --> UC7_3[Download DOCX with Diagrams]

    Admin((Admin)) --> UC8[Monitor System Health]
    Admin --> UC9[Inspect Graph State]

    System((LangGraph System)) --> UC10[Retrieve RAG Context]
    System --> UC11[Generate Diagrams]
    System --> UC12[Validate Output]
```

## Actor Descriptions

| Actor | Description |
|---|---|
| **Stakeholder** | Primary user who provides product ideas, answers questions, reviews drafts, and exports the final SRS |
| **Admin** | Secondary user who monitors system health and debugs graph execution state |
| **LangGraph System** | Automated backend system that orchestrates the 5-phase workflow, LLM calls, and RAG retrieval |

## Use Case Descriptions

| ID | Use Case | Description | Primary Actor |
|---|---|---|---|
| UC-01 | Create New SRS | Submits an informal product idea and receives a structured ingestion summary | Stakeholder |
| UC-02 | Answer Clarifying Questions | Responds to one-at-a-time elicitation questions across 4 groups (12 total) | Stakeholder |
| UC-03 | Approve Outline | Reviews the IEEE 830 outline proposal and approves or requests changes | Stakeholder |
| UC-04 | Review Draft | Reviews the complete SRS draft and provides feedback or finalization command | Stakeholder |
| UC-05 | Request Section Revision | Requests regeneration or inline edits for specific sections of the draft | Stakeholder |
| UC-06 | Finalize Document | Issues the finalize command to complete the SRS document | Stakeholder |
| UC-07 | Export SRS | Downloads the completed SRS as Markdown JSON, Markdown file, or DOCX | Stakeholder |
| UC-08 | Monitor System Health | Checks the `/health` endpoint for model name and graph readiness | Admin |
| UC-09 | Inspect Graph State | Views raw LangGraph state via the debug endpoint for troubleshooting | Admin |
| UC-10 | Retrieve RAG Context | Performs semantic search against seeded regulatory documents for context injection | LangGraph System |
| UC-11 | Generate Diagrams | Creates PlantUML and Mermaid diagrams from ingested domain data | LangGraph System |
| UC-12 | Validate Output | Runs guardrail classification on user messages and validation on generated diagrams | LangGraph System |

## System Boundary

```mermaid
flowchart LR
    subgraph ExternalActors["External Actors"]
        Stakeholder
        Admin
    end

    subgraph System["AI-Driven SRS Generator"]
        subgraph FrontendLayer["Frontend (Next.js)"]
            Auth[Authentication]
            ChatUI[Chat Workspace]
            ExportUI[Export Interface]
        end

        subgraph BackendLayer["Backend (FastAPI + LangGraph)"]
            Guardrail[Guardrail Classifier]
            Ingestion[Ingestion Engine]
            Elicitation[Elicitation Engine]
            Outline[Outline Generator]
            Drafting[Drafting Engine]
            Assembly[Document Assembly]
            Export[Export Service]
        end

        subgraph DataLayer["Data & AI"]
            DB[(PostgreSQL)]
            Vector[(ChromaDB)]
            LLM[OpenRouter API]
        end
    end

    Stakeholder --> Auth
    Stakeholder --> ChatUI
    Stakeholder --> ExportUI
    Admin --> Auth
    Admin --> ChatUI

    ChatUI --> Guardrail
    Guardrail --> Ingestion
    Ingestion --> Elicitation
    Elicitation --> Outline
    Outline --> Drafting
    Drafting --> Assembly
    Assembly --> Export

    Ingestion --> LLM
    Ingestion --> Vector
    Elicitation --> LLM
    Outline --> LLM
    Drafting --> LLM

    ChatUI --> DB
    Export --> DB
```
