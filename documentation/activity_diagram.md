# Activity Diagram

This diagram shows the main activity flow of the automated SRS generator system, covering the three run modes (full flow, diagrams-only, section revision), the 6 parallel section writers, the 4-group elicitation with one-question-at-a-time interrupts, and the HITL outline/draft review interrupts.

## Full SRS Generation Flow

```mermaid
flowchart TD
    Start([User Opens Chat]) --> CreateSession[Create Backend Session]
    CreateSession --> SendPrompt[Send Initial Product Idea]
    SendPrompt --> Guardrail{Guardrail Classifier}

    Guardrail -->|small_talk / out_of_scope / unsafe| Redirect[Return Redirect Message]
    Redirect --> SendPrompt
    Guardrail -->|relevant| Ingestion[Phase 1: Ingest and Map Domain]

    Ingestion --> Plan[Generate Elicitation Plan - 2-3 topics]
    Plan --> AskQ[Generate Single Question]

    AskQ --> InterruptQ{{INTERRUPT: Wait for User Answer}}
    InterruptQ --> UserAnswers[User Provides Answer]
    UserAnswers --> StoreAns[Classify and Store Answer]

    StoreAns --> MoreInPlan{"More Questions<br/>in Plan?"}
    MoreInPlan -->|Yes| AskQ
    MoreInPlan -->|No| MoreGroups{"More Groups?<br/>(4 total)"}

    MoreGroups -->|Yes| Plan
    MoreGroups -->|No| Outline[Phase 3: Generate IEEE 830 Outline]

    Outline --> InterruptO{{INTERRUPT: Wait for Outline Approval}}
    InterruptO -->|Not Approved| Outline
    InterruptO -->|Approved| Draft[Phase 4: Draft from Approved Outline]

    Draft --> FanOut[/"6 Parallel Section Writers"/]
    FanOut --> S1[Draft s1: Introduction - 1.1 to 1.5]
    FanOut --> S2[Draft s2: Overall Description - 2.1 to 2.5]
    FanOut --> S3FR[Draft s3: Functional Requirements]
    FanOut --> S3IF[Draft s3: External Interfaces]
    FanOut --> S3NFR[Draft s3: Non-Functional Requirements]
    FanOut --> S4[Draft s4: Appendices A, B, C]

    S1 --> FanIn[\"Fan-in: all 6 sections complete"\]
    S2 --> FanIn
    S3FR --> FanIn
    S3IF --> FanIn
    S3NFR --> FanIn
    S4 --> FanIn

    FanIn --> Present[Phase 5: Present Draft for Review]
    Present --> InterruptR{{INTERRUPT: Wait for User Feedback}}

    InterruptR -->|Request Changes| ProcessFeedback[Process Review Feedback]
    ProcessFeedback --> Present

    InterruptR -->|Finalize| Assemble[Assemble Final Document]
    Assemble --> AddTables[Append Use Case Tables]
    AddTables --> AddDiagrams[Append PlantUML + Mermaid Diagrams]
    AddDiagrams --> Format[Add Front Matter + TOC]

    Format --> SSEStream[Return Complete Event via SSE]
    SSEStream --> Persist[Persist Document and State]

    Persist --> ExportChoice{User Exports?}
    ExportChoice -->|Markdown JSON| ReturnJSON[GET /api/sessions/id/document]
    ExportChoice -->|Markdown File| ReturnMD[GET /api/sessions/id/document.md]
    ExportChoice -->|DOCX| RenderDocx[Convert to DOCX with python-docx]
    RenderDocx --> EmbedDiagrams[Render Mermaid/PlantUML to PNG]
    EmbedDiagrams --> ApplyMeta[Apply Title/Author/Comment Metadata]
    ApplyMeta --> ReturnDocx[Download DOCX File]

    ReturnJSON --> End([Done])
    ReturnMD --> End
    ReturnDocx --> End
```

## Diagrams-Only Mode

```mermaid
flowchart TD
    Start([User Requests Diagram Regeneration]) --> B[Backend Processes Request]
    B --> GenMermaid[Generate Fallback Mermaid Diagrams]
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
    Start([User Requests Section Edit]) --> B[Backend Processes Request]
    B --> Revise[Revise Selected Section - LLM rewrite with context]
    Revise --> Finalize[Finalize Document - reassemble with updated section]
    Finalize --> End([Done])
```

## Elicitation Detail (Phase 2 - One Question at a Time)

```mermaid
flowchart TD
    Start([Enter Elicitation Phase]) --> Group0{"Group 0:<br/>User Roles & Flows"}

    Group0 -->|"2-3 questions"| Plan0[Generate Question Topics]
    Plan0 --> Q0_1[Ask Question 1]
    Q0_1 --> I0_1{{INTERRUPT: Wait for Answer}}
    I0_1 --> A0_1[Store Answer]
    A0_1 --> More0{More in Plan?}
    More0 -->|Yes| Q0_1
    More0 -->|No| Group1

    Group1{"Group 1:<br/>Functional Boundaries"} --> Plan1[Generate Question Topics]
    Plan1 --> Q1_1[Ask Question 1]
    Q1_1 --> I1_1{{INTERRUPT}}
    I1_1 --> A1_1[Store Answer]
    A1_1 --> More1{More in Plan?}
    More1 -->|Yes| Q1_1
    More1 -->|No| Group2

    Group2{"Group 2:<br/>Non-Functional Requirements"} --> Plan2[Generate Question Topics]
    Plan2 --> Q2_1[Ask Question 1]
    Q2_1 --> I2_1{{INTERRUPT}}
    I2_1 --> A2_1[Store Answer]
    A2_1 --> More2{More in Plan?}
    More2 -->|Yes| Q2_1
    More2 -->|No| Group3

    Group3{"Group 3:<br/>Edge Cases & Risk"} --> Plan3[Generate Question Topics]
    Plan3 --> Q3_1[Ask Question 1]
    Q3_1 --> I3_1{{INTERRUPT}}
    I3_1 --> A3_1[Store Answer]
    A3_1 --> More3{More in Plan?}
    More3 -->|Yes| Q3_1
    More3 -->|No| Done([Proceed to Outline Generation])
```

## Process Description

1. **Ingestion (Phase 1)** - LLM extracts structured project summary (domain, actors, flows, entities, constraints) from the user's initial informal product idea.

2. **Elicitation (Phase 2)** - 4 groups of questions (2-3 questions each), asked one at a time. Each question pauses via `interrupt()` and resumes when the user provides an answer. Answers accumulate in state.

3. **Outline Review (Phase 3)** - LLM generates an IEEE 830-compliant outline. User can approve, modify, or reject sections before drafting proceeds.

4. **Drafting (Phase 4)** - 6 parallel section writers draft simultaneously using `asyncio.gather`. Each returns structured subsections with explicit numbering.

5. **Review & Refine (Phase 5)** - User reviews the assembled draft. Can request section regeneration, inline edits, or finalize the document.

6. **Finalization** - Document is assembled with:
   - Use-case catalog and detail tables derived from ingestion data
   - PlantUML diagrams (usecase, component, sequence, activity) generated from domain data
   - Mermaid diagrams (flowchart, sequence, ER, class, state) as fallback
   - Front matter with project title, document info table, and table of contents

7. **Export** - Available formats:
   - Markdown JSON (`GET /api/sessions/{id}/document`)
   - Markdown file download (`GET /api/sessions/{id}/document.md`)
   - DOCX with embedded diagrams (`GET /api/sessions/{id}/document.docx`)
