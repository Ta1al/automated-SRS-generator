# Class Diagram

This diagram shows the main implemented models, state types, and core runtime
components of the SRS generator system.

```mermaid
classDiagram
    class User {
        +id: string
        +email: string
        +name: string?
        +passwordHash: string
        +createdAt: datetime
        +updatedAt: datetime
    }

    class Chat {
        +id: string
        +userId: string
        +title: string
        +backendThreadId: string
        +currentDocument: string?
        +stateJson: json?
        +createdAt: datetime
        +updatedAt: datetime
    }

    class ChatMessage {
        +id: string
        +chatId: string
        +role: USER|ASSISTANT
        +content: string
        +createdAt: datetime
    }

    class ChatRun {
        +id: string
        +chatId: string
        +status: RUNNING|COMPLETED|FAILED|NEEDS_INPUT
        +inputMessage: string
        +revisionTarget: json?
        +currentNode: string?
        +currentNodeStarted: datetime?
        +statusEvents: json?
        +questionPrompt: string?
        +questionsJson: json?
        +etaSeconds: int?
        +errorMessage: string?
        +startedAt: datetime
        +completedAt: datetime?
    }

    class StageTimingStat {
        +node: string
        +sampleCount: int
        +avgDurationMs: float
    }

    class Requirement {
        +id: string
        +text: string
        +labels: list~string~
        +criteria: string
    }

    class ClarificationQuestion {
        +category: string
        +question: string
        +suggested_options: list~string~
        +rationale: string
    }

    class InitialElicitation {
        +project_title: string
        +project_purpose: string
        +key_stakeholders: list~string~
        +main_features: list~string~
        +constraints: list~string~
        +preliminary_glossary: list~GlossaryEntry~
    }

    class GlossaryEntry {
        +term: string
        +definition: string
    }

    class UseCase {
        +name: string
        +actor: string
        +description: string
        +trigger: string
        +precondition: string
        +basic_steps: list~string~
    }

    class SystemEnvironment {
        +description: string
        +actors: list~string~
        +external_systems: list~string~
    }

    class Section1Introduction {
        +purpose: string
        +scope: string
        +glossary: list~GlossaryEntry~
        +overview: string
    }

    class Section2OverallDescription {
        +system_environment: SystemEnvironment
        +primary_use_cases: list~UseCase~
        +user_characteristics: string
        +non_functional_overview: string
    }

    class FunctionalRequirement {
        +requirement_id: string
        +name: string
        +trigger: string
        +precondition: string
        +basic_flow: string
        +alternative_flows: list~string~
        +postcondition: string
        +exception_paths: list~string~
    }

    class NonFunctionalRequirement {
        +category: string
        +requirement: string
        +rationale: string
    }

    class Section3Requirements {
        +external_interfaces: list~string~
        +functional_requirements: list~FunctionalRequirement~
        +non_functional_requirements: list~NonFunctionalRequirement~
    }

    class VerificationEntry {
        +requirement_id: string
        +test_case: string
        +acceptance_criteria: string
    }

    class Section4Verification {
        +title: string
        +description: string
        +verification_entries: list~VerificationEntry~
    }

    class SRSState {
        +chat_history: list~BaseMessage~
        +document_buffer: string
        +missing_context: list~ClarificationQuestion~
        +requirements: list~Requirement~
        +rag_context: string
        +sections: dict~string, string~
        +mermaid_blocks: list~string~
        +mermaid_errors: list~string~
        +mermaid_correction_attempts: int
        +generate_diagrams: bool
        +diagrams_only: bool
        +revision_mode: bool
        +revision_target_section_key: string
        +revision_target_title: string
        +revision_target_content: string
        +revision_request: string
        +is_complete: bool
        +qa_gaps: list~ClarificationQuestion~
        +major_decisions_asked: bool
        +final_document: string
        +project_title: string
    }

    class GraphRuntime {
        +build_graph(checkpointer)
        +astream(...)
        +aget_state(...)
        +ainvoke(...)
    }

    class FastAPIRoutes {
        +POST /api/sessions
        +POST /api/sessions/id/interact SSE
        +DELETE /api/sessions/id
        +GET /api/sessions/id/document
        +GET /api/sessions/id/document.docx
        +GET /api/sessions/id/state
        +GET /health
    }

    class GuardrailClassifier {
        +classify(message): relevant|small_talk|out_of_scope|unsafe
        -_invoke_guardrail_llm_with_retry()
        -_classify_non_resume_message_with_llm()
    }

    class PrismaChatAPI {
        +GET/POST /api/chats
        +GET/PUT/DELETE /api/chats/id
        +POST /api/chats/id/interact
        +GET/POST /api/chats/id/messages
        +GET /api/chats/id/runs/active
        +GET /api/chats/id/export/docx
    }

    class VectorStore {
        +init_vectorstore()
        +retrieve(query): string
        -_seed_collection(collection, data_dir)
    }

    class MermaidValidation {
        +validate_mermaid_syntax(code): tuple~bool, string~
        -_run_mmdc(code): tuple~bool, string~
        -_heuristic_check(code): tuple~bool, string~
    }

    class DocxExporter {
        +markdown_to_docx_bytes(text, title, author, comments): bytes
        -_add_markdown_runs(paragraph, text)
        -_add_code_block(document, code)
        -_add_table(document, lines)
        -_render_mermaid_png(code): bytes
        -_add_mermaid_image(document, code)
    }

    class DiagramRenderer {
        +render_via_mmdc(mermaid_code): bytes
        +render_via_mermaid_ink(mermaid_code): bytes
    }

    class Settings {
        +openrouter_api_key: string
        +model_name: string
        +guardrail_model_name: string
        +db_uri: string
        +chroma_path: string
        +max_mermaid_retries: int
        +docx_title: string
        +docx_author: string
        +docx_comment: string
    }

    %% Pydantic model relationships for structured LLM output
    InitialElicitation --> "*" GlossaryEntry : contains
    Section1Introduction --> "*" GlossaryEntry : contains
    Section2OverallDescription --> SystemEnvironment : contains
    Section2OverallDescription --> "*" UseCase : contains
    Section3Requirements --> "*" FunctionalRequirement : contains
    Section3Requirements --> "*" NonFunctionalRequirement : contains
    Section4Verification --> "*" VerificationEntry : contains

    User "1" --> "*" Chat : owns
    Chat "1" --> "*" ChatMessage : contains
    Chat "1" --> "*" ChatRun : tracks
    SRSState --> "*" Requirement : contains
    SRSState --> "*" ClarificationQuestion : references
    SRSState --> InitialElicitation : uses
    SRSState --> Section1Introduction : uses
    SRSState --> Section2OverallDescription : uses
    SRSState --> Section3Requirements : uses
    SRSState --> Section4Verification : uses
    PrismaChatAPI --> User : authenticates
    PrismaChatAPI --> Chat : persists
    PrismaChatAPI --> ChatMessage : writes
    PrismaChatAPI --> ChatRun : manages
    PrismaChatAPI --> FastAPIRoutes : proxies to backend
    FastAPIRoutes --> GuardrailClassifier : classifies messages
    FastAPIRoutes --> GraphRuntime : executes
    FastAPIRoutes --> DocxExporter : exports document
    DocxExporter --> DiagramRenderer : renders diagrams
    GraphRuntime --> SRSState : reads/writes
    GraphRuntime --> VectorStore : retrieves context
    GraphRuntime --> MermaidValidation : validates diagrams
    GraphRuntime --> Settings : reads config
    GuardrailClassifier --> Settings : reads config
```

## Class Descriptions

- **User / Chat / ChatMessage / ChatRun / StageTimingStat** - Persisted Prisma
  models used by the Next.js frontend. ChatRun tracks graph execution state for
  the active run. StageTimingStat records average node durations for ETA calculation.
- **Requirement** - Atomic requirement with a taxonomy-prefixed ID (e.g. `F-001`),
  descriptive text, classification labels, and a boolean-testable acceptance criterion.
- **ClarificationQuestion** - Structured follow-up question with category, question
  text, suggested options, and rationale for asking.
- **SRSState** - Full typed state passed through every LangGraph node. Uses
  `add_messages` reducer for `chat_history` and `merge_sections` dict reducer for
  `sections`. All other fields use simple replacement.
- **GraphRuntime** - Compiled LangGraph `StateGraph` workflow built by `build_graph()`.
  Supports `astream()` for SSE streaming and `aget_state()` for state inspection.
- **FastAPIRoutes** - Backend API router providing session lifecycle, SSE graph
  interaction, document retrieval, DOCX export, and debug state inspection.
- **GuardrailClassifier** - Lightweight LLM classifier that screens user messages
  before graph invocation. Uses a separate, cheaper model with retry logic and timeout.
- **PrismaChatAPI** - Next.js API routes that authenticate users via JWT, manage
  chats and messages via Prisma, and proxy graph interactions to the backend.
- **VectorStore** - ChromaDB-based retrieval over pre-seeded standards/compliance
  corpus (IEEE 830, HIPAA, GDPR, PCI-DSS, WCAG). Uses all-MiniLM-L6-v2 embeddings.
- **MermaidValidation** - Two-tier validation: `mmdc` subprocess (primary) with
  regex-based heuristic fallback. Returns `(valid, error_message)` tuple.
- **DocxExporter** - Converts Markdown to DOCX with formatted text (bold, italic,
  code, tables), embedded Mermaid diagram PNGs, and configurable document metadata.
- **DiagramRenderer** - Renders Mermaid code to PNG via `mmdc` CLI or `mermaid.ink`
  HTTP API fallback.
- **Settings** - Pydantic `BaseSettings` class reading `.env` configuration with
  LRU-cached singleton retrieval via `get_settings()`.

## Pydantic Structured Output Models

These models enforce schema validation on LLM-generated content using LangChain's
`with_structured_output()` method. Each model is used by a corresponding graph node:

- **InitialElicitation** - Used by `elicit_requirements` to extract project metadata
  (title, purpose, stakeholders, features, constraints, preliminary glossary).
  Enables structured project bootstrapping from user input.
- **Section1Introduction** - Used by `draft_section_1` to generate IEEE 830 Section 1
  with purpose, scope, glossary entries, and overview.
- **Section2OverallDescription** - Used by `draft_section_2` to produce system context
  (environment, use cases, user characteristics, non-functional overview).
- **Section3Requirements** - Used by `draft_section_3_fr`, `draft_section_3_nfr`, and
  `draft_section_3_iface` to generate functional requirements, non-functional requirements,
  and external interfaces with structured acceptance criteria and flows.
- **Section4Verification** - Used by `draft_section_4` to produce a verification matrix
  mapping requirement IDs to test cases and acceptance criteria.
- **Nested models** - `GlossaryEntry`, `UseCase`, `SystemEnvironment`, `FunctionalRequirement`,
  `NonFunctionalRequirement`, and `VerificationEntry` are nested within the above models
  to provide fine-grained field descriptions for LLM schema generation.
