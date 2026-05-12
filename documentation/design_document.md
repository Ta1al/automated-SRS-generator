# Design Document

## 1. System Overview

The Automated SRS Generator (ASG) is a full-stack system that helps users create software requirements specifications through an interactive chat workflow. The platform combines:

- A Next.js frontend for authentication, chat interaction, and export actions.
- A FastAPI backend for orchestration, graph execution, and document generation.
- A LangGraph-based workflow for elicitation, drafting, quality checks, and diagram generation.
- A retrieval layer (RAG) to ground outputs in seeded standards and templates.
- A PostgreSQL + Prisma persistence layer for users, chats, messages, and run states.

```mermaid
flowchart LR
    User[User] --> FE[Next.js Frontend]
    FE --> API[FastAPI Backend]
    API --> Graph[LangGraph Runtime]
    Graph --> RAG[ChromaDB RAG Store]
    API --> DB[(PostgreSQL)]
    API --> Export[DOCX/Markdown Export]
    Export --> User
```

## 2. Architecture Design

The solution follows a layered architecture with clear separation between presentation, API, orchestration, and infrastructure concerns.

### Architecture Layers

- Presentation Layer: Next.js pages and chat workspace components.
- API Gateway Layer: Next.js API routes and backend FastAPI routes.
- Orchestration Layer: LangGraph nodes, state transitions, and interruption handling.
- Data and Integration Layer: Prisma/PostgreSQL, ChromaDB, Mermaid rendering, and document export.

```mermaid
flowchart TB
    subgraph Client[Client Tier]
        UI[Next.js App Router UI]
        Auth[Auth Pages and JWT Session]
    end

    subgraph Edge[Application API Tier]
        NAPI[Next.js API Routes]
        BAPI[FastAPI Routes]
    end

    subgraph Core[Orchestration Tier]
        Guard[Guardrail Classifier]
        LG[LangGraph Workflow]
        Check[Checkpoint and Run State]
    end

    subgraph Infra[Data and Integration Tier]
        PG[(PostgreSQL + Prisma)]
        VS[(ChromaDB Vector Store)]
        DOCX[DOCX Exporter]
        MMD[Mermaid Validator/Renderer]
    end

    UI --> NAPI
    Auth --> NAPI
    NAPI --> BAPI
    BAPI --> Guard
    Guard --> LG
    LG --> Check
    LG --> VS
    BAPI --> PG
    BAPI --> DOCX
    DOCX --> MMD
```

## 3. Component Design

The core runtime is composed of components that map directly to responsibilities in the generation lifecycle.

### Key Components

- Frontend Chat Workspace: Sends user prompts and displays streaming progress/results.
- API Route Proxy: Validates user session and forwards requests to backend endpoints.
- Guardrail Classifier: Filters irrelevant/unsafe input before expensive orchestration.
- Graph Runtime: Executes node graph for full generation, diagram-only mode, or revision mode.
- Vector Store Retriever: Injects standards-compliant context into prompts.
- Mermaid Validation Pipeline: Validates and retries diagram generation when syntax errors occur.
- Export Service: Produces Markdown and DOCX with embedded diagrams.

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend Chat Workspace
    participant N as Next.js API Routes
    participant B as FastAPI Backend
    participant G as Guardrail
    participant L as LangGraph Runtime
    participant V as Vector Store
    participant E as Export Service

    U->>FE: Submit idea / revision request
    FE->>N: POST /api/chats/{chatId}/interact
    N->>B: Proxy request with auth context
    B->>G: Classify input

    alt Relevant input
        G-->>B: relevant
        B->>L: Start graph execution
        L->>V: Retrieve contextual references
        V-->>L: Retrieved context
        L-->>B: Stream node progress + final document
        B-->>N: SSE/event chunks
        N-->>FE: Stream updates and output
    else Redirect path
        G-->>B: small_talk/out_of_scope/unsafe
        B-->>N: Redirect response
        N-->>FE: Show guardrail message
    end

    opt Export requested
        FE->>N: GET /api/chats/{chatId}/export/docx
        N->>B: Proxy export request
        B->>E: Convert markdown + diagrams
        E-->>B: DOCX bytes
        B-->>FE: File download
    end
```

## 4. LLM Output Validation and Structured Output

All LLM-invoking nodes use **Pydantic-based structured output** to ensure schema compliance and type safety at the LLM boundary.

### Three-Level Fallback Strategy

```mermaid
flowchart TD
    Start([LLM Node Invoked]) --> Check{with_structured_output<br/>available?}
    
    Check -->|Yes| MockCheck{Mock<br/>detected?}
    MockCheck -->|Yes| Fallback1[Fallback 1: Text LLM]
    MockCheck -->|No| Primary["Primary: LLM.with_structured_output<br/>(Pydantic model)"]
    
    Check -->|No| Fallback1
    
    Primary --> PrimarySuccess{Valid<br/>Pydantic?}
    PrimarySuccess -->|Yes| Format["Format model to<br/>Markdown output"]
    PrimarySuccess -->|No| Fallback1
    
    Fallback1 --> JSONParse{Parse JSON<br/>from text?}
    JSONParse -->|Yes| Format
    JSONParse -->|No| Fallback2["Fallback 2: Raw text"]
    
    Format --> Return([Return formatted<br/>section/data])
    Fallback2 --> Return
```

### Validation Process

1. **Pydantic Schema Definition** - Each generative node defines a Pydantic `BaseModel` with typed fields and descriptive `Field(description=...)` annotations.
2. **LLM Structured Call** - When available, `llm.with_structured_output(ModelClass)` constrains the LLM response to match the schema exactly.
3. **Mock Detection** - Checks `llm.__class__.__module__` to detect unittest.mock objects and force fallback for tests.
4. **JSON Parsing Fallback** - If structured output unavailable, calls text-based LLM and attempts manual JSON parsing.
5. **Format Conversion** - Valid Pydantic model instances are converted to formatted Markdown section text.

### Pydantic Models

| Model | Fields | Purpose |
|---|---|---|
| `InitialElicitation` | project_title, project_purpose, key_stakeholders, main_features, constraints, preliminary_glossary | Extracts project metadata in `elicit_requirements` |
| `GlossaryEntry` | term, definition | Glossary term/definition pairs |
| `Section1Introduction` | purpose, scope, glossary[], overview | IEEE 830 Section 1: Introduction |
| `UseCase` | name, actor, description, trigger, precondition, basic_steps | System use case definition |
| `SystemEnvironment` | description, actors, external_systems | Product environment context |
| `Section2OverallDescription` | system_environment, primary_use_cases[], user_characteristics, non_functional_overview | Section 2: Overall Description |
| `FunctionalRequirement` | requirement_id, name, trigger, precondition, basic_flow, alternative_flows[], postcondition, exception_paths[] | Complete functional requirement |
| `NonFunctionalRequirement` | category, requirement, rationale | Non-functional requirement (quality attribute) |
| `Section3Requirements` | external_interfaces[], functional_requirements[], non_functional_requirements[] | Section 3: Requirements (all variants: FR, NFR, interfaces) |
| `VerificationEntry` | requirement_id, test_case, acceptance_criteria | Single requirement verification mapping |
| `Section4Verification` | title, description, verification_entries[] | Section 4: Verification Matrix |

## 5. Data Design

The data model stores user ownership, conversational history, and execution state for resumable workflow runs.

### Data Entities

- User: Account identity and credentials.
- Chat: Conversation container associated with one user.
- ChatMessage: Immutable message history within a chat.
- ChatRun: Execution metadata for each generation run.
- StageTimingStat: Aggregate timing to support ETA estimation.

```mermaid
erDiagram
    USER ||--o{ CHAT : owns
    CHAT ||--o{ CHAT_MESSAGE : contains
    CHAT ||--o{ CHAT_RUN : tracks

    USER {
        string id PK
        string email
        string name
        string password_hash
        datetime created_at
        datetime updated_at
    }

    CHAT {
        string id PK
        string user_id FK
        string title
        string backend_thread_id
        text current_document
        json state_json
        datetime created_at
        datetime updated_at
    }

    CHAT_MESSAGE {
        string id PK
        string chat_id FK
        enum role
        text content
        datetime created_at
    }

    CHAT_RUN {
        string id PK
        string chat_id FK
        enum status
        text input_message
        json revision_target
        string current_node
        json status_events
        text question_prompt
        json questions_json
        int eta_seconds
        text error_message
        datetime started_at
        datetime completed_at
    }
```

## 6. Workflow Design

The workflow supports three operation modes and includes quality gates plus human-in-the-loop clarification.

### Workflow Stages

- Stage 1: Input and guardrail classification.
- Stage 2: Route to full flow, diagram regeneration, or section revision.
- Stage 3: Full flow performs retrieval, requirement extraction/classification, and section drafting.
- Stage 4: QA and completeness checks trigger clarification when required.
- Stage 5: Diagram validation/correction loop finalizes output for streaming and export.

```mermaid
flowchart TD
    Start([User Request]) --> Guardrail{Guardrail Classification}

    Guardrail -->|small_talk / out_of_scope / unsafe| Redirect[Return Redirect Message]
    Redirect --> End([Done])

    Guardrail -->|relevant| Route{Execution Mode}

    Route -->|Full Flow| Retrieve[Retrieve RAG Context]
    Retrieve --> Elicit[Elicit and Structure Requirements]
    Elicit --> Classify[Classify Requirement Labels]
    Classify --> Draft[Draft Core SRS Sections]
    Draft --> Evaluate[Completeness and QA Review]

    Evaluate --> NeedsInput{Missing Major Decisions?}
    NeedsInput -->|Yes| Ask[Ask Clarifying Questions]
    Ask --> Resume[Resume with User Answers]
    Resume --> Classify

    NeedsInput -->|No| Diagrams{Generate Diagrams?}
    Diagrams -->|Yes| Gen[Generate Mermaid Blocks]
    Gen --> Validate[Validate Mermaid Syntax]
    Validate --> Valid{Valid or Retry Budget Exhausted?}
    Valid -->|No| Correct[Correct Mermaid and Retry]
    Correct --> Validate
    Valid -->|Yes| Finalize[Assemble Final Document]

    Diagrams -->|No| Finalize

    Route -->|Diagrams-Only| Gen
    Route -->|Section Revision| Revise[Revise Target Section]
    Revise --> Finalize

    Finalize --> Stream[Stream Final Output]
    Stream --> Export[Optional DOCX/Markdown Export]
    Export --> End
```
