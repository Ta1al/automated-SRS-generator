# Data Flow Diagrams

## DFD Level 0 - System Context

```mermaid
graph LR
    User((User)) -->|Chat actions| Frontend["Next.js Web Frontend"]
    Frontend -->|Internal API requests| Api["Next.js API Routes"]
    Api -->|Session & interact calls| Backend["FastAPI + LangGraph"]
    Backend -->|SSE: status / token / question / complete| Api
    Api -->|Chat updates & final document| Frontend
    Frontend -->|Export Markdown or DOCX| User
```

## DFD Level 1 - Main Processes

```mermaid
graph TD
    User((User)) --> P1["1.0 Start or open chat"]
    P1 --> P2["2.0 Persist chat + user message"]
    P2 --> AppDB[(PostgreSQL App DB)]

    P2 --> P2a["2.1 Guardrail classifier"]
    P2a -->|small_talk / out_of_scope / unsafe| P2b["2.2 Return redirect message"]
    P2b --> User

    P2a -->|relevant| P3["3.0 Backend session interaction SSE"]
    P3 --> P3a{Resume or fresh?}
    P3a -->|Fresh invoke| Graph["4.0 LangGraph 5-phase pipeline"]
    P3a -->|Resume after interrupt| Graph

    Graph --> VectorDB[(Chroma Vector Store)]
    Graph --> LLM[OpenRouter LLM]
    Graph --> Checkpointer[(PostgreSQL Checkpointer)]

    Graph --> P5["5.0 Return stream events + final draft"]
    P5 --> P6["6.0 Persist assistant output, state, and document"]
    P6 --> AppDB

    P6 --> P7["7.0 Prepare document export"]
    P7 --> P8{Export Format?}
    P8 -->|Markdown JSON| ReturnJSON["Return Markdown JSON"]
    P8 -->|Markdown File| ReturnMD["Return Markdown file"]
    P8 -->|DOCX| DocxConvert["Convert to DOCX + render diagrams"]
    DocxConvert --> ReturnDocx["Return DOCX binary"]
    ReturnJSON --> P9["8.0 Present to user"]
    ReturnMD --> P9
    ReturnDocx --> P9
    P9 --> User
```

## DFD Level 2 - Detailed Processing

```mermaid
graph TD
    subgraph Frontend["Frontend (Next.js)"]
        UI["Chat Workspace UI"]
        FEApi["/api/chats/* routes"]
        ExportProxy["/api/chats/[id]/export/docx proxy"]
        RunTracker["/api/chats/[id]/runs/active"]
    end

    subgraph AppStorage["Application Storage"]
        PrismaDB[(PostgreSQL via Prisma)]
        RunTable["ChatRun table"]
        TimingTable["StageTimingStat table"]
    end

    subgraph Backend["Backend (FastAPI)"]
        Guardrail["Guardrail Classifier LLM"]
        Sessions["/api/sessions - create/delete"]
        Interact["/api/sessions/{id}/interact - SSE stream"]
        DocState["/api/sessions/{id}/document - Markdown JSON"]
        DocxExport["/api/sessions/{id}/document.docx - DOCX"]
        MdExport["/api/sessions/{id}/document.md - Markdown file"]
        StateDebug["/api/sessions/{id}/state - debug"]
        DocumentAssembler["Document Assembly"]
    end

    subgraph GraphExec["LangGraph 5-Phase Pipeline"]
        Ingest["Phase 1: ingest_and_map_domain"]
        Plan["Phase 2: generate_elicitation_plan"]
        AskQ["Phase 2: generate_single_elicitation_question"]
        Store["Phase 2: classify_and_store_answers"]
        Outline["Phase 3: generate_outline"]
        Approve["Phase 3: wait_for_outline_approval"]
        Draft["Phase 4: draft_from_approved_outline"]
        S1["draft_section_1"]
        S2["draft_section_2"]
        S3FR["draft_s_3_functional"]
        S3IF["draft_s_3_external"]
        S3NFR["draft_s_3_nfr"]
        S4["draft_s_4"]
        Present["Phase 5: present_draft_for_review"]
        Review["Phase 5: process_review_feedback"]
        Finalize["finalize_and_export"]
    end

    subgraph DocxProc["DOCX Processing"]
        MarkdownParse["Parse headings, lists, tables, code blocks"]
        BoldItalic["Apply bold/italic/code inline styles"]
        MermaidRender["Render Mermaid to PNG via mmdc/mermaid.ink"]
        PlantUMLRender["Render PlantUML to PNG via plantuml CLI/server"]
        EmbedImages["Embed PNG images at 6.4in width"]
        SetMetadata["Set title/author/comments from env"]
    end

    subgraph AIData["AI and Retrieval"]
        Chroma[(ChromaDB - regulatory_docs)]
        OpenRouter[OpenRouter API]
        Checkpoint[(PostgreSQL Checkpointer)]
    end

    %% Frontend flows
    UI --> FEApi
    FEApi --> PrismaDB
    FEApi --> Sessions
    FEApi --> Interact
    FEApi --> ExportProxy
    FEApi --> RunTracker
    RunTracker --> RunTable
    RunTable --> TimingTable

    ExportProxy --> DocxExport
    ExportProxy --> MdExport

    %% Backend routing
    Interact --> Guardrail
    Guardrail --> OpenRouter

    %% Phase 1
    Interact --> Ingest

    %% Phase 2
    Ingest --> Plan
    Plan --> AskQ
    AskQ --> Store
    Store -->|more questions| AskQ
    Store -->|next group| Plan
    Store -->|all done| Outline

    %% Phase 3
    Outline --> Approve
    Approve -->|not approved| Approve
    Approve -->|approved| Draft

    %% Phase 4
    Draft --> asyncio_gather["asyncio.gather"]
    asyncio_gather --> S1
    asyncio_gather --> S2
    asyncio_gather --> S3FR
    asyncio_gather --> S3IF
    asyncio_gather --> S3NFR
    asyncio_gather --> S4

    %% Phase 5
    S1 --> Present
    S2 --> Present
    S3FR --> Present
    S3IF --> Present
    S3NFR --> Present
    S4 --> Present
    Present --> Review
    Review -->|more edits| Review
    Review -->|finalize| Finalize

    %% Document assembly
    Finalize --> DocumentAssembler
    DocumentAssembler --> Interact

    %% AI/retrieval
    Ingest --> OpenRouter
    Plan --> OpenRouter
    AskQ --> OpenRouter
    Outline --> OpenRouter
    S1 --> OpenRouter
    S2 --> OpenRouter
    S3FR --> OpenRouter
    S3IF --> OpenRouter
    S3NFR --> OpenRouter
    S4 --> OpenRouter
    Ingest --> Chroma
    Interact --> Checkpoint

    %% Return data
    Interact --> FEApi
    FEApi --> DocState
    DocState --> DocumentAssembler
    DocState --> PrismaDB

    %% Export path
    DocxExport --> MarkdownParse
    MarkdownParse --> BoldItalic
    BoldItalic --> MermaidRender
    BoldItalic --> PlantUMLRender
    MermaidRender --> EmbedImages
    PlantUMLRender --> EmbedImages
    EmbedImages --> SetMetadata
    SetMetadata --> ExportProxy

    MdExport --> DocumentAssembler
    MdExport --> ExportProxy

    FEApi --> PrismaDB
    FEApi --> UI
```

## Data Store Descriptions

| Store | Type | Managed By | Contents |
|---|---|---|---|
| PostgreSQL App DB | Relational (Prisma) | Next.js | Users, Chats, Messages, Runs, Timing stats |
| PostgreSQL Checkpointer | Relational (psycopg3) | LangGraph | Graph checkpoint/state for resumability |
| ChromaDB | Vector Store | ChromaDB | Seeded regulatory documents (IEEE 830, HIPAA, GDPR, etc.) |

## Key Data Flows

1. **Session Creation** → Backend generates UUID thread_id, returned to frontend
2. **Message Interaction** → Frontend proxies message to backend SSE endpoint; backend classifies via guardrail, invokes/resumes graph, streams events back
3. **Graph Execution** → 5-phase pipeline with interrupts; state persisted to PostgreSQL checkpointer
4. **Document Assembly** → Sections combined, formatted, enriched with use-case tables and diagrams
5. **Export** → Markdown returned as JSON or file; DOCX generated with formatted text and embedded diagram images
