# Activity Diagram

This diagram shows the main activity flow of the automated SRS generator system,
covering the three run modes (full flow, diagrams-only, section revision), the
parallel fan-out of section writers, the Mermaid self-correction loop, and the
HITL clarification interrupt.

## Full SRS Generation Flow

```mermaid
flowchart TD
    Start([User Opens Chat]) --> CreateSession[Create Backend Session]
    CreateSession --> SendPrompt[Send Initial Product Idea]
    SendPrompt --> Guardrail{Guardrail Classifier}
    Guardrail -->|small_talk / out_of_scope / unsafe| Redirect[Return Redirect Message]
    Redirect --> SendPrompt
    Guardrail -->|relevant| InvokeGraph[Invoke LangGraph]

    InvokeGraph --> RouteStart{Route from Start}

    RouteStart -->|Full Flow| RAG[Retrieve RAG Context from ChromaDB]
    RAG --> Elicit[Elicit Requirements — extract entities, workflows, constraints]
    Elicit --> Classify[Classify Requirements — assign 12-label taxonomy]

    Classify --> FanOut[/"Fan-out: 5 parallel section writers"/]
    FanOut --> S1[Draft Section 1: Introduction]
    FanOut --> S2[Draft Section 2: Product Overview]
    FanOut --> S3FR[Draft Section 3.1-3.2: Functional Requirements]
    FanOut --> S3NFR[Draft Section 3.3: Quality of Service NFRs]
    FanOut --> S3IF[Draft Section 3.4: External Interfaces]

    S1 --> FanIn[\"Fan-in: all 5 sections complete"\]
    S2 --> FanIn
    S3FR --> FanIn
    S3NFR --> FanIn
    S3IF --> FanIn

    FanIn --> S4[Draft Section 4: Verification Matrix]
    S4 --> Evaluate[Evaluate Completeness — identify major decisions]

    Evaluate --> EvalDecision{Missing Major Decisions?}
    EvalDecision -->|Yes, first time| AskQuestions[Ask Clarifying Questions — HITL Interrupt]
    AskQuestions --> UserAnswers[User Provides Answers]
    UserAnswers --> Classify

    EvalDecision -->|No| DiagramDecision{Diagrams Requested?}
    DiagramDecision -->|Yes| GenMermaid[Generate 3 Mermaid Diagrams — asyncio.gather]
    DiagramDecision -->|No| Finalize

    GenMermaid --> ValidateMermaid[Validate Mermaid Syntax]
    ValidateMermaid --> MermaidOk{Valid or Budget Exhausted?}
    MermaidOk -->|Errors and retries left| CorrectMermaid[LLM Correct Mermaid Errors]
    CorrectMermaid --> ValidateMermaid
    MermaidOk -->|Yes| Finalize[Finalize Document — assemble all sections]

    Finalize --> SSEStream[Stream Final Document via SSE]
    SSEStream --> PersistResult[Persist Document and State to PostgreSQL]
    PersistResult --> ExportChoice{User Exports?}
    ExportChoice -->|Markdown| ReturnMarkdown[Download Markdown JSON]
    ExportChoice -->|DOCX| RenderDocx[Convert to DOCX with python-docx]
    RenderDocx --> EmbedDiagrams[Render Mermaid to PNG via mmdc/mermaid.ink]
    EmbedDiagrams --> ApplyMetadata[Apply Title/Author/Comment Metadata]
    ApplyMetadata --> ReturnDocx[Download DOCX File]
    ReturnMarkdown --> End([Done])
    ReturnDocx --> End
```

## Diagrams-Only Mode

```mermaid
flowchart TD
    Start([User Requests Diagram Regeneration]) --> RouteStart{Route from Start}
    RouteStart -->|diagrams_only=true| GenMermaid[Generate 3 Mermaid Diagrams]
    GenMermaid --> Validate[Validate Mermaid Syntax]
    Validate --> Decision{Valid or Budget Exhausted?}
    Decision -->|Errors and retries left| Correct[LLM Correct Mermaid]
    Correct --> Validate
    Decision -->|Yes| Finalize[Finalize Document]
    Finalize --> End([Done])
```

## Section Revision Mode

```mermaid
flowchart TD
    Start([User Requests Section Edit]) --> RouteStart{Route from Start}
    RouteStart -->|revision_mode=true| Revise[Revise Selected Section — LLM rewrite with context]
    Revise --> Finalize[Finalize Document — reassemble with updated section]
    Finalize --> End([Done])
```

## Process Description

1. **User Opens Chat** — User accesses the chat workspace through the
   authenticated frontend.
2. **Create Backend Session** — Frontend creates a backend thread/session
   (UUID) for LangGraph graph execution and checkpointing.
3. **Send Initial Prompt** — User provides their product idea or requirements.
4. **Guardrail Classifier** — A lightweight LLM classifier screens the
   message. Small talk, out-of-scope, and unsafe messages receive redirect
   responses without invoking the graph.
5. **Route from Start** — The graph entry conditional edge routes to one of
   three modes: full flow, diagrams-only, or section revision.
6. **Retrieve RAG Context** — Semantic search against the ChromaDB collection
   seeded with IEEE 830, HIPAA, GDPR, PCI-DSS, WCAG, and SRS template
   documents.
7. **Elicit Requirements** — LLM extracts entities, workflows, and constraints
   from user input into a structured outline. Also infers a project title.
8. **Classify Requirements** — LLM assigns labels from the 12-category
   taxonomy (F, A, FT, L, LF, MN, O, PE, PO, SC, SE, US) to each requirement.
9. **Fan-out: 5 Parallel Section Writers** — LangGraph's `Send` API dispatches
   all five section writers simultaneously. Each reads shared state and writes
   to a distinct section key.
10. **Fan-in → Verification Matrix** — After all five writers complete,
    `draft_section_4` generates a verification matrix mapping requirement IDs
    to verification methods (Test / Analysis / Inspection / Demonstration).
11. **Evaluate Completeness** — LLM identifies 2–5 high-impact unresolved
    architectural decisions. If major decisions are missing (and haven't been
    asked before), the graph interrupts for clarification.
12. **Clarification Loop (HITL)** — The graph pauses via `interrupt()`, sends
    questions to the user via SSE, and resumes when answers arrive. The flow
    re-enters at `classify_requirements` to redraft with enriched context.
13. **Mermaid Diagram Pipeline** — Three diagrams (architecture flowchart,
    sequence, ER) are generated concurrently via `asyncio.gather`, validated
    via `mmdc` or heuristic fallback, and corrected up to `MAX_MERMAID_RETRIES`
    times if errors exist.
14. **Finalize Document** — All section drafts and diagrams are assembled into
    the final Markdown SRS document.
15. **Export** — User can download as Markdown JSON or as DOCX with formatted
    text, embedded diagram PNGs, and configurable metadata.
