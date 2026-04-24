# Data Flow Diagrams

## DFD Level 0 — System Context

```mermaid
graph LR
    User((User)) -->|Chat actions| Frontend["Next.js Web Frontend"]
    Frontend -->|Internal API requests| Api["Next.js API Routes"]
    Api -->|Session & interact calls| Backend["FastAPI + LangGraph"]
    Backend -->|SSE: status / token / question / complete| Api
    Api -->|Chat updates & final document| Frontend
    Frontend -->|Export Markdown or DOCX| User
```

## DFD Level 1 — Main Processes

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
    P3a -->|Fresh invoke| Graph["4.0 LangGraph pipeline"]
    P3a -->|Resume after interrupt| Graph

    Graph --> VectorDB[(Chroma Vector Store)]
    Graph --> LLM[OpenRouter LLM]
    Graph --> Checkpointer[(PostgreSQL Checkpointer)]

    Graph --> P5["5.0 Return stream events + final draft"]
    P5 --> P6["6.0 Persist assistant output, state, and document"]
    P6 --> AppDB

    P6 --> P7["7.0 Prepare document export"]
    P7 --> P8{Export Format?}
    P8 -->|Markdown| ReturnMarkdown["Return Markdown JSON"]
    P8 -->|DOCX| DocxConvert["Convert to DOCX + render diagrams"]
    DocxConvert --> ReturnDocx["Return DOCX binary"]
    ReturnMarkdown --> P9["8.0 Present to user"]
    ReturnDocx --> P9
    P9 --> User
```

## DFD Level 2 — Detailed Processing

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
        Sessions["/api/sessions — create/delete"]
        Interact["/api/sessions/{id}/interact — SSE stream"]
        DocState["/api/sessions/{id}/document — Markdown"]
        DocxExport["/api/sessions/{id}/document.docx — DOCX"]
        StateDebug["/api/sessions/{id}/state — debug"]
    end

    subgraph GraphExec["LangGraph Execution"]
        RAG["retrieve_rag_context"]
        Elicit["elicit_requirements"]
        Classify["classify_requirements"]
        DraftS1["draft_section_1"]
        DraftS2["draft_section_2"]
        DraftS3FR["draft_section_3_fr"]
        DraftS3NFR["draft_section_3_nfr"]
        DraftS3IF["draft_section_3_iface"]
        DraftS4["draft_section_4"]
        Evaluate["evaluate_completeness"]
        AskClarify["ask_clarifying_questions — interrupt"]
        GenMermaid["generate_mermaid — asyncio.gather"]
        ValidateMermaid["validate_mermaid"]
        CorrectMermaid["correct_mermaid"]
        Revise["revise_selected_section"]
        Finalize["finalize_document"]
    end

    subgraph DocxProc["DOCX Processing"]
        MarkdownParse["Parse headings, lists, tables, code blocks"]
        BoldItalic["Apply bold/italic/code inline styles"]
        DiagramRender["Render Mermaid to PNG via mmdc/mermaid.ink"]
        EmbedImages["Embed PNG images at 6.4in width"]
        SetMetadata["Set title/author/comments from env"]
    end

    subgraph AIData["AI and Retrieval"]
        Chroma[(ChromaDB — regulatory_docs)]
        OpenRouter[OpenRouter API]
        Checkpoint[(PostgreSQL Checkpointer)]
    end

    UI --> FEApi
    FEApi --> PrismaDB
    FEApi --> Sessions
    FEApi --> Interact
    FEApi --> ExportProxy
    FEApi --> RunTracker
    RunTracker --> RunTable
    RunTable --> TimingTable
    
    ExportProxy --> DocxExport

    Interact --> Guardrail
    Guardrail --> OpenRouter
    Interact --> RAG
    RAG --> Elicit --> Classify
    Classify --> DraftS1
    Classify --> DraftS2
    Classify --> DraftS3FR
    Classify --> DraftS3NFR
    Classify --> DraftS3IF
    DraftS1 --> DraftS4
    DraftS2 --> DraftS4
    DraftS3FR --> DraftS4
    DraftS3NFR --> DraftS4
    DraftS3IF --> DraftS4
    DraftS4 --> Evaluate
    Evaluate --> AskClarify
    AskClarify --> Classify
    Evaluate --> GenMermaid
    Evaluate --> Finalize
    GenMermaid --> ValidateMermaid
    ValidateMermaid --> CorrectMermaid
    CorrectMermaid --> ValidateMermaid
    ValidateMermaid --> Finalize

    RAG --> Chroma
    Elicit --> OpenRouter
    Classify --> OpenRouter
    DraftS1 --> OpenRouter
    DraftS2 --> OpenRouter
    DraftS3FR --> OpenRouter
    DraftS3NFR --> OpenRouter
    DraftS3IF --> OpenRouter
    DraftS4 --> OpenRouter
    Evaluate --> OpenRouter
    GenMermaid --> OpenRouter
    CorrectMermaid --> OpenRouter
    Revise --> OpenRouter
    Interact --> Checkpoint

    Finalize --> Interact
    Interact --> FEApi
    FEApi --> DocState
    DocState --> PrismaDB
    
    DocxExport --> MarkdownParse
    MarkdownParse --> BoldItalic
    BoldItalic --> DiagramRender
    DiagramRender --> EmbedImages
    EmbedImages --> SetMetadata
    SetMetadata --> ExportProxy
    
    FEApi --> PrismaDB
    FEApi --> UI
```
