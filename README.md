# AI-Driven SRS Generator

Automated Software Requirements Specification generator powered by **LangGraph**,
**FastAPI**, and **OpenRouter**. Converts a vague stakeholder idea into a full
IEEE 830-compliant SRS document via recursive multi-agent elicitation.

The retrieval corpus is pre-seeded with regulatory and standards guidance,
including HIPAA, GDPR, PCI-DSS, WCAG, IEEE 830, and an extended SRS authoring
template.

---

## Table of Contents

- [Architecture](#architecture)
  - [System overview](#system-overview)
  - [Graph topology](#graph-topology)
  - [Run modes](#run-modes)
- [Project Structure](#project-structure)
- [Backend](#backend)
  - [Entry point and lifespan](#entry-point-and-lifespan)
  - [Configuration](#configuration)
  - [LangGraph state schema](#langgraph-state-schema)
  - [Graph nodes](#graph-nodes)
  - [RAG and vector store](#rag-and-vector-store)
  - [Mermaid validation](#mermaid-validation)
  - [DOCX export](#docx-export)
  - [Guardrail classifier](#guardrail-classifier)
  - [Database and checkpointing](#database-and-checkpointing)
- [Frontend](#frontend)
  - [Pages and components](#pages-and-components)
  - [Authentication](#authentication)
  - [Frontend API routes](#frontend-api-routes)
  - [Prisma schema](#prisma-schema)
  - [Backend integration and SSE](#backend-integration-and-sse)
- [Setup](#setup)
- [API](#api)
  - [SSE event types](#sse-event-types)
  - [Example flow](#example-flow)
- [Tests](#tests)
- [Requirement taxonomy labels](#requirement-taxonomy-labels)
- [Technology stack](#technology-stack)

---

## Architecture

### System overview

```mermaid
flowchart LR
    User[User] -->|HTTP + SSE| Frontend[Next.js Frontend]
    Frontend -->|REST to internal API| PrismaApi[Next.js API Routes]
    PrismaApi -->|Session + chat persistence| PgApp[(PostgreSQL App DB)]
    PrismaApi -->|Proxy /api/sessions/*| FastAPI[FastAPI Backend]

    FastAPI -->|Guardrail check| Guardrail[Guardrail Classifier LLM]
    FastAPI -->|Compile + execute| Graph[LangGraph StateGraph]
    Graph -->|LLM calls| OpenRouter[OpenRouter Model]
    Graph -->|RAG retrieval| Chroma[(ChromaDB Vector Store)]
    Graph -->|Checkpoint state| PgCheckpoint[(PostgreSQL Checkpointer)]
    
    Frontend -->|Download document.docx| FastAPI
    FastAPI -->|DOCX export with metadata| DocxExport[python-docx]
    DocxExport -->|Render diagrams| MermaidRender[mmdc / mermaid.ink]
```

The system is a full-stack application with two independently running processes:

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | Next.js 16, React 19, Prisma | Landing page, auth, chat workspace, SSE consumption, export proxy |
| **Backend** | FastAPI, LangGraph, LangChain | Session management, guardrail classification, graph execution, SSE streaming, DOCX export |
| **Database** | PostgreSQL 16 | Shared instance - Prisma tables for app data, LangGraph checkpoint tables for graph state |
| **Vector Store** | ChromaDB (all-MiniLM-L6-v2) | Persistent local collection seeded with regulatory/standards documents |
| **LLM Provider** | OpenRouter API | Main model for generation nodes + lightweight guardrail model for message classification |

### Graph topology

The LangGraph `StateGraph` is a **5-phase workflow** with user interrupts at key decision points:

**Phase 1: Ingestion** → **Phase 2: Elicitation (Q&A)** → **Phase 3: Outline approval** → **Phase 4: Drafting** → **Phase 5: Review & feedback** → **Finalization** → END

```mermaid
flowchart TD
    START([START]) --> ingest["ingest_and_map_domain"]
    ingest --> plan["generate_elicitation_plan"]
    plan --> q["generate_single_elicitation_question"]
    q --> store["classify_and_store_answers"]
    
    store -->|more questions in plan| q
    store -->|next group| plan
    store -->|all done| outline["generate_outline"]
    
    outline --> wait["wait_for_outline_approval"]
    wait -->|not approved| wait
    wait -->|approved| draft["draft_from_approved_outline"]
    
    draft --> present["present_draft_for_review"]
    present --> review["process_review_feedback"]
    
    review -->|more revisions| review
    review -->|finalize| finalize["finalize_and_export"]
    
    finalize --> END([END])
```

User interrupts via `interrupt()` occur at:
- After `wait_for_outline_approval` (pause for outline approval decision)
- After `present_draft_for_review` (pause for feedback collection)

## Diagrams

Architecture and design diagrams live in the `documentation/` folder and use **Mermaid** syntax. Key diagram files:

- `documentation/activity_diagram.md` — overall activity/run modes
- `documentation/class_diagram.md` — system class/data diagrams
- `documentation/dataflow_diagram.md` — dataflow overview
- `documentation/er_diagram.md` — entity-relationship diagram
- `documentation/use_case_diagram.md` — high-level use-case overview

Render Mermaid diagrams locally with the Mermaid CLI (`mmdc`) or preview in https://mermaid.live. Example:

```bash
# npm install -g @mermaid-js/mermaid-cli
mmdc -i documentation/activity_diagram.md -o documentation/diagrams/activity_diagram.png
```

### Run modes

The 5-phase workflow supports the following modes:

| Mode | Execution Path | Description |
|---|---|---|
| **Full flow** (default) | `ingest_and_map_domain` → all 5 phases → `finalize_and_export` | Complete SRS generation from initial idea through review |
| **Resume after interrupt** | Re-enters at paused node (e.g., `wait_for_outline_approval`) | Continues workflow after user provides approval/feedback |

Note: Alternative modes (diagrams-only, targeted section revision) were removed in the 5-phase redesign. All workflows now follow the standard progression with structured user interrupts.

---

## Project Structure

```
├── app/                          # Python backend (FastAPI + LangGraph)
│   ├── main.py                   # FastAPI entry point, lifespan manager
│   ├── config.py                 # Pydantic Settings (reads .env)
│   ├── api/
│   │   └── routes.py             # REST + SSE endpoints, guardrail classifier
│   ├── graph/
│   │   ├── state.py              # SRSState TypedDict, Requirement, ClarificationQuestion
│   │   ├── graph.py              # StateGraph builder, conditional edges, fan-out
│   │   ├── nodes.py              # Graph node implementations + output normalizers
│   │   └── prompts.py            # System prompts for every LLM-calling node
│   ├── rag/
│   │   ├── vectorstore.py        # ChromaDB init, seeding, semantic retrieval
│   │   ├── mermaid_syntax.py     # In-memory Mermaid syntax corpus
│   │   └── seed_data/            # Pre-seeded .txt files (ieee_830, hipaa, gdpr, …)
│   ├── validation/
│   │   └── mermaid.py            # mmdc subprocess validation + regex fallback
│   ├── export/
│   │   └── docx.py               # Markdown → DOCX conversion with diagram embedding
│   ├── db/
│   │   └── checkpointer.py       # AsyncPostgresSaver pool management
│   └── tests/
│       └── test_main.py          # pytest + pytest-asyncio test suite
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
│   │   │   ├── chat-workspace.tsx # Main 3-column workspace component
│   │   │   └── theme-toggle.tsx  # Dark/light theme toggle
│   │   └── lib/
│   │       ├── auth.ts           # JWT session management (jose, HS256)
│   │       ├── backend.ts        # Backend fetch wrapper + SSE stream parser
│   │       ├── chat-runner.ts    # Graph run orchestration, stage ordering, ETA
│   │       ├── config.ts         # Environment constants
│   │       ├── http.ts           # HTTP utility functions
│   │       ├── api-route.ts      # API route helpers
│   │       └── prisma.ts         # Prisma client singleton
│   ├── prisma/
│   │   ├── schema.prisma         # Database models (User, Chat, ChatMessage, ChatRun, …)
│   │   └── init_auth_chat.sql    # Idempotent SQL init script
│   └── package.json              # Next.js 16, React 19, Prisma, mermaid, zod, …
├── documentation/                # Architecture diagrams (Mermaid)
│   ├── activity_diagram.md
│   ├── class_diagram.md
│   ├── dataflow_diagram.md
│   └── er_diagram.md
├── docker-compose.yml            # PostgreSQL 16 service
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
└── README.md                     # This file
```

---

## Backend

### Entry point and lifespan

**`app/main.py`** creates the FastAPI application with a lifespan context
manager that runs three startup tasks in order:

1. **Initialise ChromaDB** - calls `init_vectorstore()` which creates or opens
   the persistent `regulatory_docs` collection and seeds it with the `.txt`
   files from `app/rag/seed_data/` (IEEE 830, HIPAA, GDPR, PCI-DSS, WCAG,
   SRS template). Seeding splits each file into paragraphs and upserts them
   with source metadata.
2. **Open PostgreSQL pool** - `managed_checkpointer()` opens an async
   connection pool (`psycopg3`, min 2 / max 10 connections) and creates
   `AsyncPostgresSaver` checkpoint tables (idempotent).
3. **Compile graph** - `build_graph(checkpointer)` wires all nodes and edges
   into a `CompiledGraph` stored on `app.state.graph`.

On shutdown the checkpointer pool is closed automatically by the async context
manager.

CORS is configured from `CORS_ORIGINS` (comma-separated, defaults to
`http://localhost:3000`). The app also registers a `/health` endpoint returning
the configured model name and graph readiness status.

### Configuration

**`app/config.py`** uses `pydantic-settings` with `BaseSettings` to read `.env`:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter API key |
| `MODEL_NAME` | *(required)* | Main OpenRouter model slug (e.g. `openai/gpt-4o-mini`) |
| `GUARDRAIL_MODEL_NAME` | *(required)* | Lightweight model for guardrail classification |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Timeout for guardrail classifier calls |
| `DB_URI` | `postgresql+psycopg://…` | PostgreSQL connection URI (psycopg3 driver) |
| `CHROMA_PATH` | `.chroma` | ChromaDB persistence directory |
| `CHROMA_COLLECTION` | `regulatory_docs` | ChromaDB collection name |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `APP_RELOAD` | `false` | Enable hot-reload for development |
| `CORS_ORIGINS` | `http://localhost:3000,…` | Allowed CORS origins (comma-separated) |
| `DOCX_TITLE` | `SRS` | Document title embedded in DOCX metadata |
| `DOCX_AUTHOR` | `SRS Generator` | Author embedded in DOCX metadata |
| `DOCX_COMMENT` | `Generated by AI SRS Generator` | Comment embedded in DOCX metadata |
| `MAX_MERMAID_RETRIES` | `3` | Maximum Mermaid diagram correction attempts |

### LangGraph state schema

**`app/graph/state.py`** defines `SRSState`, a `TypedDict` that flows through
every node. Nodes receive the full state and return a partial update which
LangGraph merges back using annotated reducers.

| Field | Type | Reducer | Purpose |
|---|---|---|---|
| `chat_history` | `list[BaseMessage]` | `add_messages` (append) | Full user ↔ AI conversation |
| `document_buffer` | `str` | replace | Raw working draft from elicitor |
| `missing_context` | `list[ClarificationQuestion]` | replace | Follow-up questions from evaluator |
| `requirements` | `list[Requirement]` | replace | Parsed atomic requirements with IDs, labels, criteria |
| `rag_context` | `str` | replace | Retrieved regulatory text from ChromaDB |
| `sections` | `dict[str, str]` | `merge_sections` (dict merge) | Keyed Markdown drafts (`s1`, `s2`, `s3_fr`, `s3_nfr`, `s3_iface`, `s4`) |
| `mermaid_blocks` | `list[str]` | replace | Raw Mermaid code (architecture, sequence, ER) |
| `mermaid_errors` | `list[str]` | replace | Validation errors aligned by index |
| `mermaid_correction_attempts` | `int` | replace | Counter for correction loop budget |
| `generate_diagrams` | `bool` | replace | Enable Mermaid generation in full flow |
| `diagrams_only` | `bool` | replace | Skip drafting, only generate diagrams |
| `revision_mode` | `bool` | replace | Skip full flow, revise one section |
| `revision_target_section_key` | `str` | replace | Section key to revise (`s1`, `s2`, …) |
| `revision_target_title` | `str` | replace | Human-readable section title |
| `revision_target_content` | `str` | replace | Current content of the section |
| `revision_request` | `str` | replace | User's requested change |
| `is_complete` | `bool` | replace | Set by evaluator when draft is ready |
| `qa_gaps` | `list[ClarificationQuestion]` | replace | Gaps found during evaluation |
| `major_decisions_asked` | `bool` | replace | Prevents repeated clarification loops |
| `final_document` | `str` | replace | Assembled Markdown SRS output |
| `project_title` | `str` | replace | LLM-inferred project title |

Supporting types:

- **`Requirement`** - `{id, text, labels, criteria}` where `id` uses the
  taxonomy prefix (e.g. `F-001`, `SE-003`).
- **`ClarificationQuestion`** - `{category, question, suggested_options, rationale}`.

### Structured output and Pydantic models

All LLM-invoking nodes in `nodes.py` use LangChain's **`with_structured_output()`** method to enforce output validation through Pydantic models. This approach:

- **Primary strategy**: Uses the LLM's native structured output mode (when available) to constrain responses to schema-validated Pydantic models.
- **Fallback 1**: Text-based LLM call with manual JSON parsing if structured output fails.
- **Fallback 2**: Raw text output if both structured and JSON parsing fail.
- **Mock detection**: Detects unittest.mock objects to prevent test failures by forcing fallback paths.

Implemented Pydantic models:

| Model | Purpose | Used by |
|---|---|---|
| `InitialElicitation` | Project metadata extraction | `elicit_requirements` |
| `Section1Introduction` | IEEE 830 Section 1 structure | `draft_section_1` |
| `Section2OverallDescription` | Product overview with use cases | `draft_section_2` |
| `Section3Requirements` | Requirements with flows and acceptance criteria | `draft_section_3_fr`, `draft_section_3_nfr`, `draft_section_3_iface` |
| `Section4Verification` | Verification matrix with test mappings | `draft_section_4` |
| `GlossaryEntry` | Term and definition pairs | `Section1Introduction` (nested) |
| `UseCase` | System use case details | `Section2OverallDescription` (nested) |
| `SystemEnvironment` | System context and actors | `Section2OverallDescription` (nested) |
| `FunctionalRequirement` | Complete FR with flows | `Section3Requirements` (nested) |
| `NonFunctionalRequirement` | NFR with category and rationale | `Section3Requirements` (nested) |
| `VerificationEntry` | Test case and acceptance criteria | `Section4Verification` (nested) |

Each model uses Pydantic `Field` descriptions to guide LLM output schema generation. The structured approach ensures:

- Type safety at the LLM output boundary
- Consistent JSON structure for parsing and formatting
- Clear validation error messages when LLM outputs don't conform to schema
- Backward compatibility through multi-level fallback strategy

### Graph nodes

**`app/graph/nodes.py`** implements all node functions. Each is an async
function that receives `SRSState` and returns a partial state update.

| Node | Phase | LLM | Purpose |
|---|---|---|---|
| `ingest_and_map_domain` | 1 (Ingestion) | ✓ | Extracts project metadata (title, scope, stakeholders, features, constraints) from initial user input |
| `generate_elicitation_plan` | 2 (Elicitation) | ✓ | Creates a list of topics/questions for the next elicitation group |
| `generate_single_elicitation_question` | 2 (Elicitation) | ✓ | Generates one focused elicitation question (one-at-a-time for user interaction) |
| `classify_and_store_answers` | 2 (Elicitation) | ✓ | Parses and stores user's answer to the elicitation question |
| `generate_outline` | 3 (Outline) | ✓ | Drafts a high-level SRS outline based on collected answers |
| `wait_for_outline_approval` | 3 (Outline) | - | Pauses via `interrupt()` to collect user outline approval/rejection (HITL) |
| `draft_from_approved_outline` | 4 (Drafting) | ✓ | Writes the full SRS document (all sections) from the approved outline |
| `present_draft_for_review` | 5 (Review) | - | Surfaces draft to user and collects feedback via `interrupt()` (HITL) |
| `process_review_feedback` | 5 (Review) | ✓ | Processes user feedback and applies targeted revisions to the document |
| `finalize_and_export` | Finalization | - | Assembles final SRS and exports to Markdown + DOCX |


Key helper functions and patterns in `nodes.py`:

- `_llm_invoke_structured()` - Calls LLM with structured output (`with_structured_output()`) using a Pydantic model for schema validation, with fallback to text parsing.
- `_llm_invoke_text()` - Calls LLM in text mode and manually parses JSON from response.
- `_normalize_message_text()` - Normalizes and lowercases user input for command matching (e.g., `OUTLINE_APPROVE_COMMAND`).
- `_latest_human_message()` - Retrieves the most recent user message from chat history.

Interrupt patterns:

- `wait_for_outline_approval()` uses `interrupt(value=...)` to pause and await user approval/rejection via `OUTLINE_APPROVE_COMMAND`.
- `present_draft_for_review()` uses `interrupt()` to collect user feedback and revision targets.

### RAG and vector store

**`app/rag/vectorstore.py`** manages a persistent ChromaDB collection named
`regulatory_docs` using the default `all-MiniLM-L6-v2` embedding model (no
external API needed).

**Seed data** in `app/rag/seed_data/`:

| File | Content |
|---|---|
| `ieee_830.txt` | IEEE 830 SRS standard structure and guidance |
| `hipaa.txt` | HIPAA healthcare compliance requirements |
| `gdpr.txt` | GDPR data protection regulation |
| `pci_dss.txt` | PCI-DSS payment card security standard |
| `wcag.txt` | WCAG web accessibility guidelines |
| `srs_template.txt` | Extended SRS authoring template with section guidance |

Seed data is split into paragraphs and upserted with source metadata on
startup. The `retrieve()` function performs semantic similarity search and
returns concatenated chunks with source attribution, which is injected into
prompts via the `rag_context` state field.

**`app/rag/mermaid_syntax.py`** provides a lightweight in-memory corpus of
Mermaid syntax rules (10–15 examples per diagram type: flowchart, sequence, ER)
used during diagram generation.

### Mermaid validation

**`app/validation/mermaid.py`** validates generated Mermaid diagrams using a
two-tier strategy:

1. **Primary** - Runs `mmdc` (mermaid-cli) as an async subprocess with a 20-second
   timeout. Requires `npm install -g @mermaid-js/mermaid-cli`.
2. **Fallback** - Regex-based heuristic check (bracket balance, diagram type
   detection) when `mmdc` is not available. Supports flowchart, sequenceDiagram,
   erDiagram, classDiagram, stateDiagram, gantt, and more.

Invalid diagrams trigger the `correct_mermaid` → `validate_mermaid` retry loop
(up to `MAX_MERMAID_RETRIES` attempts).

### DOCX export

**`app/export/docx.py`** converts the final Markdown SRS into a formatted Word
document using `python-docx`:

- Parses headings (H1–H4), paragraphs, bullet lists, numbered lists, code
  blocks, and pipe-delimited tables.
- Applies inline formatting: **bold**, *italic*, `code` (Consolas font).
- Renders Mermaid diagram blocks to PNG and embeds them at 6.4″ width:
  1. Attempts `mmdc` subprocess rendering first.
  2. Falls back to `mermaid.ink` HTTP API (base64-encoded URL).
- Sets document metadata (title, author, comments) from environment
  configuration.

### Guardrail classifier

Before invoking the LangGraph workflow, each non-resume user message passes
through a lightweight guardrail LLM classifier (`GUARDRAIL_MODEL_NAME`) that
returns one of four labels:

| Label | Action |
|---|---|
| `relevant` | Message proceeds to the graph |
| `small_talk` | Returns a friendly redirect response |
| `out_of_scope` | Returns a scope reminder response |
| `unsafe` | Returns a scope reminder response |

The classifier uses a separate, cheaper model with a configurable timeout
(`GUARDRAIL_TIMEOUT_SECONDS`, default 20s). On classifier failure, the message
is allowed through to avoid blocking the user.

### Database and checkpointing

**`app/db/checkpointer.py`** provides `managed_checkpointer()`, an async
context manager that:

1. Opens a `psycopg3` `AsyncConnectionPool` (min 2, max 10 connections,
   `autocommit=True` for `CREATE INDEX CONCURRENTLY`).
2. Creates an `AsyncPostgresSaver` and runs `.setup()` to create LangGraph
   checkpoint tables (idempotent).
3. Yields the checkpointer for use by the graph builder.
4. Closes the pool on exit.

The same PostgreSQL instance hosts both the LangGraph checkpoint tables and the
Prisma-managed application tables (User, Chat, ChatMessage, ChatRun,
StageTimingStat).

---

## Frontend

### Pages and components

| Route | Component | Description |
|---|---|---|
| `/` | `page.tsx` | Landing page with hero section, feature cards, CTA buttons |
| `/login` | `login/page.tsx` | Email/password login form |
| `/signup` | `signup/page.tsx` | User registration form |
| `/chat` | `chat/page.tsx` → `ChatWorkspace` | Protected 3-column workspace (auth-gated, redirects to `/login`) |

**`ChatWorkspace`** (`src/components/chat-workspace.tsx`) is the main
interactive component with three columns:

- **Left sidebar** - List of previous chats for the current user, with a
  "New Chat" button.
- **Center panel** - Active chat conversation with message history, input
  field, real-time status updates (node progress, ETA estimation), and
  clarification question prompts (HITL interrupt handling).
- **Right panel** - Live SRS section preview cards (6 sections: s1, s2,
  s3_iface, s3_fr, s3_nfr, s4), Markdown document viewer, and export buttons
  (Markdown download, DOCX download). Supports targeted section revision mode.

### Authentication

**`src/lib/auth.ts`** implements JWT-based session management:

- Tokens are signed with HS256 using `AUTH_SECRET` from the environment.
- JWTs carry `{ userId, email }` and expire after 7 days.
- The session cookie `srs_auth` is `httpOnly`, `sameSite=lax`, and `secure` in
  production.
- `getSessionUser()` retrieves the current user from the cookie and verifies
  the JWT signature.
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
| `/api/chats/[chatId]/interact` | POST | Proxy user message to backend, handle SSE stream, persist messages and run state |
| `/api/chats/[chatId]/messages` | GET, POST | Retrieve or add chat messages |
| `/api/chats/[chatId]/runs/active` | GET | Get the latest active `ChatRun` (RUNNING or NEEDS_INPUT) |
| `/api/chats/[chatId]/runs/active/stream` | GET | Resume SSE streaming for an active run |
| `/api/chats/[chatId]/export/docx` | GET | Proxy to backend DOCX export endpoint |

### Prisma schema

**`frontend/prisma/schema.prisma`** defines five models:

- **User** - `id` (CUID PK), `email` (unique), `name?`, `passwordHash`,
  timestamps. One-to-many with Chat.
- **Chat** - `id` (CUID PK), `userId` (FK → User, cascade delete), `title`,
  `backendThreadId` (unique, links to backend session UUID), `currentDocument?`,
  `stateJson?` (JSONB). One-to-many with ChatMessage and ChatRun. Indexed on
  `(userId, updatedAt)`.
- **ChatMessage** - `id` (CUID PK), `chatId` (FK → Chat, cascade delete),
  `role` (enum: USER | ASSISTANT), `content`, `createdAt`. Indexed on
  `(chatId, createdAt)`.
- **ChatRun** - `id` (CUID PK), `chatId` (FK → Chat, cascade delete),
  `status` (enum: RUNNING | COMPLETED | FAILED | NEEDS_INPUT),
  `inputMessage`, `revisionTarget?` (JSONB), `currentNode?`,
  `currentNodeStarted?`, `statusEvents?` (JSONB), `questionPrompt?`,
  `questionsJson?` (JSONB), `etaSeconds?`, `errorMessage?`, timestamps.
  Indexed on `(chatId, startedAt DESC)` and `(chatId, status)`.
- **StageTimingStat** - `node` (PK), `sampleCount`, `avgDurationMs`,
  timestamps. Tracks average node execution duration for ETA estimation.

### Backend integration and SSE

**`src/lib/backend.ts`** provides:

- `backendFetch()` - Wrapper around `fetch()` using `BACKEND_API_URL`.
- `consumeSseResponse()` - Parses the SSE stream from the backend interact
  endpoint. Handles events: `token`, `status`, `project_title`, `question`,
  `complete`, `result`, `error`. Accumulates assistant text and final document.
  Normalises clarification questions into structured
  `ClarificationQuestion` objects.

**`src/lib/chat-runner.ts`** manages graph run orchestration:

- Defines ordered stage lists for each run mode: `ORDERED_STAGES_FULL` (16
  stages), `ORDERED_STAGES_NO_DIAGRAMS` (14 stages),
  `ORDERED_STAGES_DIAGRAMS_ONLY` (4 stages),
  `ORDERED_STAGES_SECTION_REVISION` (2 stages).
- Identifies `PARALLEL_DRAFT_STAGES` (the 5 section writers that run
  concurrently) and maps them to section keys via `DRAFT_NODE_TO_SECTION_KEY`.
- Calculates ETA based on node timings and stage order.

---

## Setup

### 1. Prerequisites

- Python 3.11 or 3.13
- Node.js 20+
- Docker (for PostgreSQL)
- `npm install -g @mermaid-js/mermaid-cli` *(optional - enables strict Mermaid validation and DOCX diagram rendering)*

### 2. Install dependencies

```bash
# Backend
pip install -r requirements.txt
# On Windows - install chromadb binary first (avoids C++ compiler requirement):
#   pip install chromadb --prefer-binary

# Frontend
cd frontend && npm install && cd ..
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY, MODEL_NAME, GUARDRAIL_MODEL_NAME
# Optional DOCX metadata: DOCX_TITLE, DOCX_AUTHOR, DOCX_COMMENT
```

For the frontend, copy `frontend/.env.example` to `frontend/.env` (local
defaults are pre-filled):

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

Server starts at `http://localhost:8000`.
Interactive API docs: `http://localhost:8000/docs`.
ReDoc docs: `http://localhost:8000/redoc`.

### 7. Start the frontend

```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Create a new elicitation session (returns `{"thread_id": "<uuid>"}`) |
| `POST` | `/api/sessions/{id}/interact` | Send a message; stream SSE response. Supports modes: full, diagrams-only, section revision |
| `DELETE` | `/api/sessions/{id}` | Delete persisted session checkpoint state |
| `GET` | `/api/sessions/{id}/document` | Retrieve the completed SRS as Markdown JSON |
| `GET` | `/api/sessions/{id}/document.docx` | Download the completed SRS as DOCX with embedded diagrams |
| `GET` | `/api/sessions/{id}/state` | Debug - inspect raw LangGraph state |
| `GET` | `/health` | Health check (returns model name and graph readiness) |

The interact endpoint accepts `InteractRequest` with the following fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `message` | `string` | *(required)* | User message text |
| `mode` | `string` | `"full"` | Run mode: `full`, `diagrams_only`, or `section_revision` |
| `generate_diagrams` | `bool` | `false` | Include Mermaid diagram generation in the full flow |
| `section_seed` | `object?` | - | Pre-existing section data for revision |
| `revision_*` | various | - | Revision target metadata (section key, title, content, request) |

### SSE event types

| Event | Payload | Description |
|---|---|---|
| `token` | `{"content": "...", "node": "..."}` | Streamed LLM text chunk |
| `status` | `{"node": "...", "status": "finished"}` | Node completion notification |
| `project_title` | `{"project_title": "..."}` | LLM-inferred project title |
| `question` | `{"questions": [...], "prompt": "..."}` | Clarifying questions (HITL interrupt) |
| `complete` | `{"document": "..."}` | Final SRS Markdown document |
| `error` | `{"message": "..."}` | Runtime error |

### Example flow

```bash
# 1. Create session
curl -X POST http://localhost:8000/api/sessions
# → {"thread_id": "<uuid>"}

# 2. Start elicitation (replace <thread_id>)
curl -X POST http://localhost:8000/api/sessions/<thread_id>/interact \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to build a food delivery app for restaurants"}' \
  --no-buffer

# 3. Answer clarifying questions (uses same thread_id)
curl -X POST http://localhost:8000/api/sessions/<thread_id>/interact \
  -H "Content-Type: application/json" \
  -d '{"message": "Auth via email/password. Expect 10k daily users. GDPR applies."}' \
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

## Requirement taxonomy labels

The classifier assigns one or more labels from this taxonomy to each atomic
requirement:

| Prefix | Category | Description |
|---|---|---|
| `F` | Functional | Observable system behaviour, business logic, data processing |
| `A` | Availability | Uptime SLA, redundancy, regional failover |
| `FT` | Fault Tolerance | Partial-failure behaviour, circuit breakers, graceful degradation |
| `L` | Legal / Compliance | Regulatory compliance (GDPR, HIPAA, PCI-DSS, SOX) |
| `LF` | Look & Feel | UI/UX constraints, brand guidelines, WCAG accessibility |
| `MN` | Maintainability | Code modularity, documentation, deployment pipeline |
| `O` | Operational | Logging, monitoring, disaster recovery, backup |
| `PE` | Performance | Numeric latency/throughput/resource thresholds (e.g. <200 ms at P95) |
| `PO` | Portability | Cross-platform, multi-cloud, OS compatibility |
| `SC` | Scalability | Load handling growth (e.g. 500k concurrent users) |
| `SE` | Security | Cryptography, access control, vulnerability protection |
| `US` | Usability | User adoption metrics, training requirements, SUS scores |

---

## Technology stack

### Backend

| Package | Version | Purpose |
|---|---|---|
| FastAPI | 0.115.8 | Web framework, REST + SSE endpoints |
| Uvicorn | 0.34.0 | ASGI server |
| sse-starlette | 2.2.1 | Server-Sent Events support |
| LangChain | 0.3.19 | LLM abstraction layer |
| LangChain-OpenAI | 0.3.7 | OpenRouter / OpenAI chat model integration |
| LangGraph | 1.0.10rc1 | Stateful multi-agent workflow orchestration |
| langgraph-checkpoint-postgres | 2.0.10 | PostgreSQL-backed graph state persistence |
| psycopg | 3.2.4 | PostgreSQL driver (async, binary, connection pool) |
| ChromaDB | 0.6.3 | Vector store with built-in all-MiniLM-L6-v2 embeddings |
| Pydantic | 2.10.6 | Data validation and settings management |
| python-docx | 1.2.0 | DOCX document generation |
| httpx | 0.28.1 | Async HTTP client (mermaid.ink fallback, guardrail retries) |

### Frontend

| Package | Version | Purpose |
|---|---|---|
| Next.js | 16.1.7 | React framework with App Router and API routes |
| React | 19.2.3 | UI rendering |
| Prisma | 6.16.2 | PostgreSQL ORM and schema management |
| jose | 6.2.1 | JWT signing and verification (HS256) |
| bcryptjs | 3.0.3 | Password hashing |
| react-markdown | 10.1.0 | Markdown rendering in chat and document preview |
| remark-gfm | 4.0.1 | GitHub Flavored Markdown support (tables, strikethrough) |
| mermaid | 11.12.0 | Client-side Mermaid diagram rendering |
| zod | 4.3.6 | Runtime schema validation |
| Tailwind CSS | 4 | Utility-first CSS framework |

### Infrastructure

| Component | Version | Purpose |
|---|---|---|
| PostgreSQL | 16 | Shared database for app data (Prisma) and graph checkpoints |
| Docker Compose | - | PostgreSQL container orchestration |
| OpenRouter API | - | LLM provider (supports OpenAI, Anthropic, and other models) |
