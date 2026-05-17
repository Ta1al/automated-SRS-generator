# Use Case Diagram

## High-Level System Use Cases

```mermaid
graph TD
    User((Stakeholder)) --> UC1[Create New SRS]
    User --> UC2[Answer Clarifying Questions]
    User --> UC3[Review Draft]
    User --> UC4[Request Section Revision]
    User --> UC5[Finalize Document]
    User --> UC6[Export SRS]

    UC1 --> UC1_1[Submit Product Idea]
    UC1 --> UC1_2[Review Ingested Summary]

    UC2 --> UC2_1[Provide User Roles & Flows]
    UC2 --> UC2_2[Define Functional Boundaries]
    UC2 --> UC2_3[Specify NFRs]
    UC2 --> UC2_4[Identify Edge Cases]

    UC6 --> UC6_1[Download Markdown JSON]
    UC6 --> UC6_2[Download Markdown File]
    UC6 --> UC6_3[Download DOCX with Diagrams]

    Admin((Admin)) --> UC7[Monitor System Health]
    Admin --> UC8[Inspect Graph State]

    System((LangGraph System)) --> UC9[Retrieve RAG Context]
    System --> UC10[Generate Diagrams]
    System --> UC11[Validate Output]
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
| UC-02 | Answer Clarifying Questions | Responds to one-at-a-time elicitation questions across 4 groups | Stakeholder |
| UC-03 | Review Draft | Reviews the complete SRS draft and provides feedback or finalization command | Stakeholder |
| UC-04 | Request Section Revision | Requests regeneration or inline edits for specific sections of the draft | Stakeholder |
| UC-05 | Finalize Document | Issues the finalize command to complete the SRS document | Stakeholder |
| UC-06 | Export SRS | Downloads the completed SRS as Markdown JSON, Markdown file, or DOCX | Stakeholder |
| UC-07 | Monitor System Health | Checks the `/health` endpoint for model name and graph readiness | Admin |
| UC-08 | Inspect Graph State | Views raw LangGraph state via the debug endpoint for troubleshooting | Admin |
| UC-09 | Retrieve RAG Context | Performs semantic search against seeded regulatory documents for context injection | LangGraph System |
| UC-10 | Generate Diagrams | Creates Mermaid and PlantUML diagrams from ingested domain data | LangGraph System |
| UC-11 | Validate Output | Runs guardrail classification on user messages and validation on generated diagrams | LangGraph System |

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
    Elicitation --> Drafting
    Drafting --> Assembly
    Assembly --> Export

    Ingestion --> LLM
    Ingestion --> Vector
    Elicitation --> LLM
    Drafting --> LLM

    ChatUI --> DB
    Export --> DB
```
