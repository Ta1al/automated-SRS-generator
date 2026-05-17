# AI-Driven SRS Generator

Automated Software Requirements Specification generator powered by **LangGraph**, **FastAPI**, and **OpenRouter**. Converts a vague stakeholder idea into a full IEEE 830-compliant SRS document via a 5-phase recursive multi-agent elicitation workflow with human-in-the-loop interrupts.

## Table of Contents

- [Architecture](#architecture)
  - [System overview](#system-overview)
  - [5-Phase workflow](#5-phase-workflow)
  - [Graph topology](#graph-topology)
- [Project Structure](#project-structure)
- [Backend](#backend)
  - [Entry point and lifespan](#entry-point-and-lifespan)
  - [Configuration](#configuration)
  - [LangGraph state schema](#langgraph-state-schema)
  - [Graph nodes](#graph-nodes)
  - [LLM structured output](#llm-structured-output)
  - [RAG and vector store](#rag-and-vector-store)
  - [Guardrail classifier](#guardrail-classifier)
  - [Document assembly and formatting](#document-assembly-and-formatting)
  - [DOCX export](#docx-export)
  - [Database and checkpointing](#database-and-checkpointing)
- [Frontend](#frontend)
  - [Pages and components](#pages-and-components)
  - [Authentication](#authentication)
  - [Frontend API routes](#frontend-api-routes)
  - [Prisma schema](#prisma-schema)
  - [Chat runner and SSE consumption](#chat-runner-and-sse-consumption)
- [Setup](#setup)
- [API](#api)
  - [SSE event types](#sse-event-types)
  - [Example flow](#example-flow)
- [Tests](#tests)
- [Diagrams](#diagrams)
- [Technology stack](#technology-stack)

---

## Architecture

### System overview

```mermaid
flowchart LR
    User[User] -->|HTTP + SSE| Frontend[Next.js Frontend]
    Frontend -->|REST to internal API| PrismaApi[Next.js API Routes]
    PrismaApi -->|Session + chat persistence| PgApp[(PostgreSQL App DB)]
    PrismaApi -->|Proxy interact + export| FastAPI[FastAPI Backend]

    FastAPI -->|Guardrail check| Guardrail[Guardrail Classifier LLM]
    FastAPI -->|Compile + execute| Graph[LangGraph StateGraph]
    Graph -->|LLM calls| OpenRouter[OpenRouter Model]
    Graph -->|RAG retrieval| Chroma[(ChromaDB Vector Store)]
    Graph -->|Checkpoint state| PgCheckpoint[(PostgreSQL Checkpointer)]

    Frontend -->|Download document| FastAPI
    FastAPI -->|DOCX export with metadata| DocxExport[python-docx]
    FastAPI -->|Markdown download| MdExport[Markdown export]
    DocxExport -->|Render diagrams| DiagramRender[mmdc / mermaid.ink / plantuml]
```

The system is a full-stack application with two independently running processes:

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | Next.js 16, React 19, Prisma | Landing page, auth, chat workspace, SSE consumption, export proxy |
| **Backend** | FastAPI, LangGraph, LangChain | Session management, guardrail classification, graph execution, SSE streaming, DOCX/Markdown export |
| **Database** | PostgreSQL 16 | Shared instance - Prisma tables for app data, LangGraph checkpoint tables for graph state |
| **Vector Store** | ChromaDB (all-MiniLM-L6-v2) | Persistent local collection seeded with regulatory/standards documents |
| **LLM Provider** | OpenRouter API | Main model for generation nodes + lightweight guardrail model for message classification |

### 5-Phase workflow

The LangGraph `StateGraph` follows a strict 5-phase progression:

**Phase 1 (Ingestion)** → **Phase 2 (Elicitation: 4 Q&A groups, one question at a time)** → **Phase 3 (Outline review + approval)** → **Phase 4 (Drafting: 6 parallel section writers)** → **Phase 5 (Review + refine loop)** → **Finalization** → END

User interrupts (`interrupt()`) occur at:
- After each elicitation question (4 groups × 2-3 questions each)
- After outline generation (wait for approval)
- After draft completion (wait for feedback/finalization)

### Graph topology

```mermaid
flowchart TD
    START([START]) --> ingest["ingest_and_map_domain"]
    ingest --> plan["generate_elicitation_plan"]
    plan --> q["generate_single_elicitation_question"]

    q -->|interrupt: wait for user answer| store["classify_and_store_answers"]

    store -->|more questions in plan| q
    store -->|next group| plan
    store -->|all 4 groups done| outline["generate_outline"]

    outline --> wait["wait_for_outline_approval"]
    wait -->|interrupt: not approved| wait
    wait -->|approved| draft["draft_from_approved_outline"]

    draft -->|6 parallel sections: s1, s2, s3_functional, s3_external, s3_nfr, s4| present["present_draft_for_review"]
    present --> review["process_review_feedback"]

    review -->|interrupt: more edits| review
    review -->|interrupt: finalize| finalize["finalize_and_export"]

    finalize --> END([END])
```

**Elicitation groups:**

| Group | Category | Topics |
|---|---|---|
| 0 | User Roles & Flows | Target users, core workflows, actors |
| 1 | Functional Boundaries | Feature scope, integrations, interfaces |
| 2 | Non-Functional Requirements | Performance, security, scalability, compliance |
| 3 | Edge Cases & Risk Mitigation | Error handling, failure modes, constraints |

---

## Project Structure

```
├── app/                          # Python backend (FastAPI + LangGraph)
│   ├── main.py                   # FastAPI entry point, lifespan manager
│   ├── config.py                 # Pydantic Settings (reads .env)
│   ├── formatting.py             # Heading numbering + SRS body formatting
│   ├── api/
│   │   └── routes.py             # REST + SSE endpoints, guardrail classifier, document assembly
│   ├── graph/
│   │   ├── state.py              # SRSState TypedDict, reducers, supporting types
│   │   ├── graph.py              # StateGraph builder, conditional edges, routing
│   │   ├── nodes.py              # Graph node implementations + Pydantic models
│   │   └── prompts.py            # System prompts for every LLM-calling node
│   ├── rag/
│   │   ├── vectorstore.py        # ChromaDB init, seeding, semantic retrieval
│   │   ├── mermaid_syntax.py     # In-memory Mermaid syntax corpus
│   │   └── seed_data/            # Pre-seeded .txt files (ieee_830, hipaa, gdpr, ...)
│   ├── validation/
│   │   └── mermaid.py            # mmdc subprocess validation + regex fallback
│   ├── export/
│   │   └── docx.py               # Markdown → DOCX with diagram embedding
│   ├── db/
│   │   └── checkpointer.py       # AsyncPostgresSaver + SQLite fallback
│   └── tests/
│       ├── test_main.py          # pytest test suite
│       └── test_finalize_state.py  # Finalization + export tests
├── frontend/                     # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Landing page
│   │   │   ├── login/page.tsx    # Login page
│   │   │   ├── signup/page.tsx   # Signup page
│   │   │   ├── chat/page.tsx     # Protected chat workspace
│   │   │   └── api/              # Next.js API routes
│   │   │       ├── auth/         # signup, login, logout, me
│   │   │       └── chats/        # CRUD, interact proxy, messages, runs, export
│   │   ├── components/
│   │   │   ├── chat-workspace.tsx # Main 3-column workspace
│   │   │   └── theme-toggle.tsx  # Dark/light theme toggle
│   │   └── lib/
│   │       ├── auth.ts           # JWT session management (jose, HS256)
│   │       ├── backend.ts        # Backend fetch wrapper + SSE stream parser
│   │       ├── chat-runner.ts    # Graph run orchestration, SSE consumption, ETA
│   │       ├── config.ts         # Environment constants
│   │       ├── http.ts           # HTTP utility functions
│   │       ├── api-route.ts      # API route helpers
│   │       └── prisma.ts         # Prisma client singleton
│   ├── prisma/
│   │   ├── schema.prisma         # Database models (User, Chat, ChatMessage, ChatRun, ...)
│   │   └── init_auth_chat.sql    # Idempotent SQL init script
│   └── package.json              # Next.js 16, React 19, Prisma, mermaid, zod
├── documentation/                # Architecture diagrams (Mermaid)
│   ├── design_document.md        # Comprehensive design document
│   ├── activity_diagram.md       # Activity flow diagrams
│   ├── class_diagram.md          # Class/data model diagrams
│   ├── dataflow_diagram.md       # Data flow diagrams
│   ├── er_diagram.md             # Entity-relationship diagram
│   └── use_case_diagram.md       # Use-case overview
├── docker-compose.yml            # PostgreSQL 16 service
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
└── README.md                     # This file
```

---

## Backend

### Entry point and lifespan

**`app/main.py`** creates the FastAPI application with a lifespan context manager that runs three startup tasks in order:

1. **Initialise ChromaDB** - calls `init_vectorstore()` which creates or opens the persistent `regulatory_docs` collection and seeds it with `.txt` files from `app/rag/seed_data/`.
2. **Open PostgreSQL pool** - `managed_checkpointer()` opens an async connection pool (`psycopg3`, min 2 / max 10 connections) and creates `AsyncPostgresSaver` checkpoint tables.
3. **Compile graph** - `build_graph(checkpointer)` wires all nodes and edges into a `CompiledGraph` stored on `app.state.graph`.

If PostgreSQL is unavailable, falls back to in-memory SQLite (`MemorySaver`) for local development.

On Windows, switches to `SelectorEventLoop` (required by psycopg3).

CORS is configured from `CORS_ORIGINS` (comma-separated). The app registers a `/health` endpoint returning the configured model name and graph readiness status.

### Configuration

**`app/config.py`** uses `pydantic-settings` with `BaseSettings` to read `.env`:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter API key |
| `MODEL_NAME` | *(required)* | Main OpenRouter model slug (e.g. `openai/gpt-4o-mini`) |
| `GUARDRAIL_MODEL_NAME` | *(required)* | Lightweight model for guardrail classification |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Timeout for guardrail classifier calls |
| `DB_URI` | `postgresql+psycopg://…` | PostgreSQL connection URI |
| `CHROMA_PATH` | `.chroma` | ChromaDB persistence directory |
| `CHROMA_COLLECTION` | `regulatory_docs` | ChromaDB collection name |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `APP_RELOAD` | `false` | Enable hot-reload for development |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `DOCX_TITLE` | `SRS` | Document title embedded in DOCX metadata |
| `DOCX_AUTHOR` | `SRS Generator` | Author embedded in DOCX metadata |
| `DOCX_COMMENT` | `Generated by AI SRS Generator` | Comment embedded in DOCX metadata |
| `MAX_MERMAID_RETRIES` | `3` | Maximum Mermaid diagram correction attempts |

### LangGraph state schema

**`app/graph/state.py`** defines `SRSState`, a `TypedDict` that flows through every node. Custom reducers: `merge_sections`, `merge_dicts`, `merge_lists`, and `add_messages` (for chat history).

| Field | Type | Reducer | Purpose |
|---|---|---|---|
| `current_phase` | `str` | replace | `ingestion` \| `elicitation` \| `outline_review` \| `drafting` \| `review_refine` \| `complete` |
| `ingestion_summary` | `dict` | `merge_dicts` | Extracted domain, actors, platform needs, core flows |
| `pending_group_index` | `int` | replace | Current elicitation group (0–3, 4 = complete) |
| `elicitation_answers` | `dict` | `merge_dicts` | Accumulated answers keyed by group (`group_0`–`group_3`) |
| `elicitation_question_plan` | `list[str]` | `merge_lists` | Question topics for current group |
| `elicitation_question_index` | `int` | replace | Current question within group |
| `outline_items` | `list[OutlineItem]` | `merge_lists` | Proposed IEEE 830 outline sections |
| `outline_approved` | `bool` | replace | Gate that blocks drafting until True |
| `sections` | `dict[str, str]` | `merge_sections` | Keyed Markdown: `s1`, `s2`, `s3_functional`, `s3_external`, `s3_nfr`, `s4` |
| `section_structures` | `dict[str, list[dict]]` | `merge_sections` | Structured subsections with number/title/content |
| `plantumul_diagrams` | `dict[str, str]` | `merge_dicts` | PlantUML diagram code (usecase, component, sequence, activity) |
| `mermaid_blocks` | `list[str]` | `merge_lists` | Mermaid diagram code strings |
| `mermaid_errors` | `list[str]` | `merge_lists` | Validation errors aligned with blocks |
| `revision_targets` | `list[str]` | `merge_lists` | Sections user wants to regenerate |
| `chat_history` | `list[BaseMessage]` | `add_messages` | Full user ↔ AI conversation |
| `requirements` | `list[Requirement]` | `merge_lists` | Parsed atomic requirements |
| `rag_context` | `str` | replace | Retrieved regulatory text from ChromaDB |

Supporting types: `CoreFlow`, `IngestionSummary`, `ClarificationQuestion`, `OutlineItem`, `Requirement`.

### Graph nodes

**`app/graph/nodes.py`** implements 10 node functions. Each is async, receives `SRSState`, and returns a partial state update.

| Node | Phase | LLM | Purpose |
|---|---|---|---|
| `ingest_and_map_domain` | 1 (Ingestion) | ✓ | Extracts project title, domain, actors, flows, constraints via `IngestionSummaryModel` |
| `generate_elicitation_plan` | 2 (Elicitation) | ✓ | Generates 2-3 question topics for current group via `QuestionPlanModel` |
| `generate_single_elicitation_question` | 2 (Elicitation) | ✓ | Asks one question, interrupts for user answer via `ClarificationQuestionModel` |
| `classify_and_store_answers` | 2 (Elicitation) | - | Stores user answer in `elicitation_answers[group_N]` |
| `generate_outline` | 3 (Outline) | ✓ | Generates IEEE 830 outline with include/exclude toggles via `OutlineListModel` |
| `wait_for_outline_approval` | 3 (Outline) | - | Interrupts for user approval; checks for approval commands/keywords |
| `draft_from_approved_outline` | 4 (Drafting) | ✓ | Runs 6 parallel section drafters via `asyncio.gather` using `DraftSectionModel` |
| `present_draft_for_review` | 5 (Review) | - | Assembles draft sections into a readable document for user review |
| `process_review_feedback` | 5 (Review) | ✓ | Interrupts for feedback; routes to regeneration or finalization |
| `finalize_and_export` | Finalization | - | Assembles final SRS with use-case tables, diagrams, front matter |

### LLM structured output

All LLM-invoking nodes use LangChain's `with_structured_output(method="json_mode")` to enforce Pydantic schema validation. A retry loop (2 retries with decreasing temperature) handles validation failures.

Key Pydantic models:

| Model | Purpose |
|---|---|
| `IngestionSummaryModel` | Project metadata extraction (title, domain, actors, flows, constraints, entities) |
| `QuestionPlanModel` | 2-3 question topics for an elicitation group |
| `ClarificationQuestionModel` | Single question with category, suggested options, rationale |
| `OutlineItemModel` | IEEE 830 section with ID, title, description, include toggle |
| `OutlineListModel` | Full list of outline items |
| `SubsectionContent` | Numbered subsection with title and Markdown content |
| `DraftSectionModel` | List of subsections for one SRS section |

### RAG and vector store

**`app/rag/vectorstore.py`** manages a persistent ChromaDB collection named `regulatory_docs` using `all-MiniLM-L6-v2` embeddings.

**Seed data** in `app/rag/seed_data/`:

| File | Content |
|---|---|
| `ieee_830.txt` | IEEE 830 SRS standard structure and guidance |
| `hipaa.txt` | HIPAA healthcare compliance requirements |
| `gdpr.txt` | GDPR data protection regulation |
| `pci_dss.txt` | PCI-DSS payment card security standard |
| `wcag.txt` | WCAG web accessibility guidelines |
| `srs_template.txt` | Extended SRS authoring template with section guidance |

The `retrieve()` function performs semantic similarity search (top 5 results) and returns concatenated chunks with source attribution.

**`app/rag/mermaid_syntax.py`** provides a lightweight in-memory corpus of Mermaid syntax rules for `flowchart`, `sequence`, and `er` diagram types.

### Guardrail classifier

Before invoking the LangGraph workflow, each non-resume user message passes through a lightweight LLM classifier (`GUARDRAIL_MODEL_NAME`) that returns one of four labels via JSON-structured output:

| Label | Action |
|---|---|
| `relevant` | Message proceeds to the graph |
| `small_talk` | Returns a friendly redirect response |
| `out_of_scope` | Returns a scope reminder response |
| `unsafe` | Returns a scope reminder response |

The classifier uses a separate, cheaper model with retry logic (2 attempts, exponential backoff) and configurable timeout (default 20s). On classifier failure, the message is allowed through unless `DISABLE_FALLBACKS` is set.

### Document assembly and formatting

**`app/api/routes.py`** contains document assembly logic:

- `_append_use_case_tables_to_document()` - Generates use-case catalog and detail tables from ingestion data
- `_append_diagrams_to_document()` - Appends PlantUML and Mermaid diagram blocks
- `_format_srs_document()` - Wraps with title, document info table, and table of contents
- `_fallback_mermaid_diagrams()` - Generates fallback Mermaid diagrams (flowchart, sequence, ER, class, state, component)

**`app/formatting.py`** provides:
- `assemble_document_from_sections()` - Concatenates 6 section drafts in order (shared by nodes and routes)
- `number_headings()` - Hierarchically numbers Markdown headings
- `split_functional_requirements()` - Restructures inline requirement markers into list items
- `format_srs_body()` - Applies both splitting and numbering

### DOCX export

**`app/export/docx.py`** converts the final Markdown SRS into a formatted Word document using `python-docx`:

- Parses headings (H1-H6), paragraphs, bullet lists, numbered lists, code blocks, blockquotes, and pipe-delimited tables.
- Applies inline formatting: **bold**, *italic*, `code` (Consolas font).
- Renders Mermaid diagrams to PNG via `mmdc` CLI (primary) or `mermaid.ink` HTTP API (fallback).
- Renders PlantUML diagrams via local `plantuml` CLI or `plantuml.com` server (fallback).
- Sets document metadata (title, author, comments) from environment configuration.

### Database and checkpointing

**`app/db/checkpointer.py`** provides two context managers:
- `managed_checkpointer()` - PostgreSQL-backed `AsyncPostgresSaver` with connection pool (min 2, max 10, autocommit)
- `managed_sqlite_checkpointer()` - In-memory `MemorySaver` fallback (data does not persist)

The same PostgreSQL instance hosts both LangGraph checkpoint tables and Prisma-managed application tables.

---

## Frontend

### Pages and components

| Route | Component | Description |
|---|---|---|
| `/` | `page.tsx` | Landing page with hero section, feature cards, CTA buttons |
| `/login` | `login/page.tsx` | Email/password login form |
| `/signup` | `signup/page.tsx` | User registration form |
| `/chat` | `chat/page.tsx` → `ChatWorkspace` | Protected 3-column workspace (auth-gated) |

**`ChatWorkspace`** (`src/components/chat-workspace.tsx`) is the main interactive component with three columns:

- **Left sidebar** - List of previous chats for the current user, "New Chat" button.
- **Center panel** - Active chat conversation with message history, input field, real-time status updates (node progress, ETA estimation), and clarification question prompts (HITL interrupt handling).
- **Right panel** - Live SRS section preview cards (6 sections), Markdown document viewer, and export buttons (Markdown download, DOCX download). Supports targeted section revision mode.

### Authentication

**`src/lib/auth.ts`** implements JWT-based session management:

- Tokens signed with HS256 using `AUTH_SECRET` from the environment.
- JWTs carry `{ userId, email }` and expire after 7 days.
- Session cookie `srs_auth` is `httpOnly`, `sameSite=lax`, `secure` in production.
- `getSessionUser()` retrieves the current user from the cookie and verifies the JWT signature.
- Passwords are hashed with `bcryptjs`.

### Frontend API routes

All frontend API routes live under `src/app/api/`:

| Route | Methods | Description |
|---|---|---|
| `/api/auth/signup` | POST | Register a new user (bcrypt hash) |
| `/api/auth/login` | POST | Authenticate and set session cookie |
| `/api/auth/logout` | POST | Clear session cookie |
| `/api/auth/me` | GET | Return current user info from JWT |
| `/api/chats` | GET, POST | List user's chats (sorted by `updatedAt` DESC) or create a new chat |
| `/api/chats/[chatId]` | GET, PUT, DELETE | Retrieve, update (title/state/document), or delete a chat |
| `/api/chats/[chatId]/interact` | POST | Creates ChatRun, fires background SSE task, returns immediately |
| `/api/chats/[chatId]/messages` | GET, POST | Retrieve or add chat messages |
| `/api/chats/[chatId]/runs/active` | GET | Get the latest active ChatRun (RUNNING or NEEDS_INPUT) |
| `/api/chats/[chatId]/runs/active/stream` | GET | Resume SSE streaming for an active run |
| `/api/chats/[chatId]/export/docx` | GET | Proxy to backend DOCX export endpoint |

### Prisma schema

**`frontend/prisma/schema.prisma`** defines five models:

- **User** - `id` (CUID PK), `email` (unique), `name?`, `passwordHash`, timestamps. One-to-many with Chat.
- **Chat** - `id` (CUID PK), `userId` (FK → User, cascade delete), `title`, `backendThreadId` (unique), `currentDocument?`, `stateJson?` (JSON). One-to-many with ChatMessage and ChatRun. Indexed on `(userId, updatedAt)`.
- **ChatMessage** - `id` (CUID PK), `chatId` (FK → Chat, cascade delete), `role` (enum: USER \| ASSISTANT), `content`, `createdAt`. Indexed on `(chatId, createdAt)`.
- **ChatRun** - `id` (CUID PK), `chatId` (FK → Chat, cascade delete), `status` (enum: RUNNING \| COMPLETED \| FAILED \| NEEDS_INPUT), `inputMessage`, `revisionTarget?` (JSON), `currentNode?`, `currentNodeStarted?`, `statusEvents?` (JSON), `questionPrompt?`, `questionsJson?` (JSON), `etaSeconds?`, `errorMessage?`, timestamps. Indexed on `(chatId, startedAt DESC)` and `(chatId, status)`.
- **StageTimingStat** - `node` (PK), `sampleCount`, `avgDurationMs`, timestamps. Tracks EMA of node durations for ETA estimation.

### Chat runner and SSE consumption

**`src/lib/chat-runner.ts`** is the core orchestration module:

1. Determines run mode: `full`, `diagrams_only`, or `section_revision`.
2. Loads timing estimates from `StageTimingStat` table.
3. Calls backend `POST /api/sessions/{thread_id}/interact` with SSE streaming.
4. Processes SSE events (`token`, `status`, `question`, `complete`, `error`).
5. Persists live section content to `stateJson.live_sections` in real-time (debounced at 500ms).
6. Tracks node start/finish times for progress and ETA calculation (exponential moving average).
7. On completion: fetches final state from backend, persists document, summary message, and updates chat metadata.

**`src/lib/backend.ts`** provides `backendFetch()` and `consumeSseResponse()` which parses the SSE stream and emits typed callbacks: `onToken`, `onStatus`, `onQuestion`, `onComplete`, `onProjectTitle`, `onError`.

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for PostgreSQL)
- `npm install -g @mermaid-js/mermaid-cli` *(optional - enables strict Mermaid validation and DOCX diagram rendering)*

### 2. Install dependencies

```bash
# Backend
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY, MODEL_NAME, GUARDRAIL_MODEL_NAME
```

For the frontend, copy `frontend/.env.example` to `frontend/.env`:

```bash
DATABASE_URL="postgresql://srs_user:srs_pass@localhost:5432/srs_db"
AUTH_SECRET="dev-local-secret-change-me"
BACKEND_API_URL="http://localhost:8000"
```

### 4. Start PostgreSQL

```bash
docker compose up -d
```

### 5. Initialise the frontend database (first run only)

```bash
cd frontend
npm run prisma:generate
cd ..
docker compose exec -T postgres psql -U srs_user -d srs_db -f frontend/prisma/init_auth_chat.sql
```

### 6. Start the backend

```bash
python -m app.main
```

Server starts at `http://localhost:8000`. Interactive API docs: `http://localhost:8000/docs`.

### 7. Start the frontend

```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## API

### Backend endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Create a new elicitation session (returns `{"thread_id": "<uuid>"}`) |
| `POST` | `/api/sessions/{id}/interact` | Send a message; stream SSE response. Supports modes: full, diagrams-only, section revision |
| `DELETE` | `/api/sessions/{id}` | Delete persisted session checkpoint state |
| `GET` | `/api/sessions/{id}/document` | Retrieve the completed SRS as Markdown JSON |
| `GET` | `/api/sessions/{id}/document.docx` | Download the completed SRS as DOCX with embedded diagrams |
| `GET` | `/api/sessions/{id}/document.md` | Download the completed SRS as Markdown file |
| `GET` | `/api/sessions/{id}/state` | Debug - inspect raw LangGraph state |
| `GET` | `/health` | Health check (returns model name and graph readiness) |

### Interact request body

| Field | Type | Default | Description |
|---|---|---|---|
| `message` | `string` | *(required)* | User message text |
| `mode` | `string` | `"full"` | Run mode: `full`, `diagrams_only`, or `section_revision` |
| `generate_diagrams` | `bool` | `false` | Include Mermaid diagram generation |
| `section_seed` | `object?` | - | Pre-existing section data for revision |
| `revision_mode` | `bool` | `false` | Enable section revision mode |
| `revision_target_section_key` | `string?` | - | Section key to revise |
| `revision_target_title` | `string?` | - | Human-readable section title |
| `revision_target_content` | `string?` | - | Current content of the section |

### SSE event types

| Event | Payload | Description |
|---|---|---|
| `token` | `{"content": "...", "node": "..."}` | Streamed LLM text chunk (or guardrail redirect) |
| `status` | `{"node": "...", "status": "started"\|"finished", "step": 1, "total_steps": 16, "estimated_remaining_ms": 30000}` | Node progress with ETA |
| `project_title` | `{"project_title": "..."}` | LLM-inferred project title |
| `question` | `{"questions": [...], "prompt": "...", "outline": {...}}` | HITL interrupt (clarification or outline review) |
| `complete` | `{"document": "..."}` | Final SRS Markdown document |
| `error` | `{"message": "...", "retryable": true}` | Runtime error |

### Example flow

```bash
# 1. Create session
curl -X POST http://localhost:8000/api/sessions
# → {"thread_id": "<uuid>"}

# 2. Start elicitation (replace <thread_id>)
curl -X POST http://localhost:8000/api/sessions/<thread_id>/interact \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to build a food delivery app"}' \
  --no-buffer

# 3. Answer clarifying questions (uses same thread_id)
curl -X POST http://localhost:8000/api/sessions/<thread_id>/interact \
  -H "Content-Type: application/json" \
  -d '{"message": "Auth via email/password. Expect 10k daily users."}' \
  --no-buffer

# 4. Retrieve final document
curl http://localhost:8000/api/sessions/<thread_id>/document

# 5. Download as DOCX
curl -o srs.docx http://localhost:8000/api/sessions/<thread_id>/document.docx
```

---

## Tests

```bash
python -m pytest app/tests/ -v
```

---

## Diagrams

Architecture and design diagrams live in the `documentation/` folder and use **Mermaid** syntax:

- `documentation/design_document.md` — Comprehensive system design
- `documentation/activity_diagram.md` — Activity flow for all run modes
- `documentation/class_diagram.md` — Class/data model diagram
- `documentation/dataflow_diagram.md` — Data flow diagrams (Level 0-2)
- `documentation/er_diagram.md` — Entity-relationship diagram
- `documentation/use_case_diagram.md` — Use-case overview

Render Mermaid diagrams locally:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i documentation/activity_diagram.md -o documentation/diagrams/activity_diagram.png
```

---

## Technology stack

### Backend

| Package | Version | Purpose |
|---|---|---|
| FastAPI | 0.115.8 | Web framework, REST + SSE endpoints |
| Uvicorn | 0.34.0 | ASGI server |
| sse-starlette | 2.2.1 | Server-Sent Events support |
| LangChain | 0.3.19 | LLM abstraction layer |
| LangChain-OpenAI | 1.1.14 | OpenRouter / OpenAI chat model integration |
| LangGraph | 1.0.10rc1 | Stateful multi-agent workflow orchestration |
| langgraph-checkpoint-postgres | 2.0.10 | PostgreSQL-backed graph state persistence |
| psycopg (binary, pool) | 3.2.4 | PostgreSQL driver (async, connection pool) |
| ChromaDB | 0.6.3 | Vector store with built-in all-MiniLM-L6-v2 embeddings |
| Pydantic | 2.10.6 | Data validation and settings management |
| python-docx | 1.2.0 | DOCX document generation |
| httpx | 0.28.1 | Async HTTP client |

### Frontend

| Package | Version | Purpose |
|---|---|---|
| Next.js | 16.2.3 | React framework with App Router and API routes |
| React | 19.2.3 | UI rendering |
| Prisma | 6.16.2 | PostgreSQL ORM and schema management |
| jose | 6.2.1 | JWT signing and verification (HS256) |
| bcryptjs | 3.0.3 | Password hashing |
| react-markdown | 10.1.0 | Markdown rendering in chat and document preview |
| remark-gfm | 4.0.1 | GitHub Flavored Markdown support |
| mermaid | 11.12.0 | Client-side Mermaid diagram rendering |
| zod | 4.3.6 | Runtime schema validation |
| Tailwind CSS | 4 | Utility-first CSS framework |

### Infrastructure

| Component | Version | Purpose |
|---|---|---|
| PostgreSQL | 16 | Shared database for app data (Prisma) and graph checkpoints |
| Docker Compose | - | PostgreSQL container orchestration |
| OpenRouter API | - | LLM provider (supports OpenAI, Anthropic, and other models) |
