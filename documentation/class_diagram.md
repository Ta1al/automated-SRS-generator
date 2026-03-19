# Class Diagram

This diagram shows the main implemented models and core runtime components.

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

    class SRSState {
        +chat_history: BaseMessage[]
        +document_buffer: string
        +missing_context: ClarificationQuestion[]
        +requirements: Requirement[]
        +rag_context: string
        +sections: map
        +mermaid_blocks: string[]
        +mermaid_errors: string[]
        +is_complete: bool
        +final_document: string
    }

    class GraphRuntime {
        +build_graph(checkpointer)
        +astream(...)
        +aget_state(...)
    }

    class FastAPIRoutes {
        +create_session()
        +interact() SSE
        +get_document()
        +get_state()
    }

    class PrismaChatAPI {
        +GET/POST chats
        +POST interact
        +GET messages
        +DELETE chat
    }

    class VectorStore {
        +init_vectorstore()
        +retrieve(query)
    }

    class MermaidValidation {
        +validate_mermaid_syntax()
    }

    class DocxExporter {
        +markdown_to_docx_bytes(text, title, author, comments)
        +_add_markdown_runs(paragraph, text)
        +_render_mermaid_png_via_mmdc(code)
        +_render_mermaid_png_via_mermaid_ink(code)
        +_add_mermaid_image(document, code)
    }

    class DiagramRenderer {
        +render_via_mmdc(mermaid_code): bytes
        +render_via_mermaid_ink(mermaid_code): bytes
    }

    User "1" --> "*" Chat : owns
    Chat "1" --> "*" ChatMessage : contains
    PrismaChatAPI --> User : authenticates
    PrismaChatAPI --> Chat : persists
    PrismaChatAPI --> ChatMessage : writes
    PrismaChatAPI --> FastAPIRoutes : proxies to backend
    FastAPIRoutes --> GraphRuntime : executes
    FastAPIRoutes --> DocxExporter : exports document
    DocxExporter --> DiagramRenderer : renders diagrams
    GraphRuntime --> SRSState : reads/writes
    GraphRuntime --> VectorStore : retrieves context
    GraphRuntime --> MermaidValidation : validates diagrams
```

## Class Descriptions

- **User / Chat / ChatMessage** - Persisted Prisma models used by the Next.js app
- **SRSState** - Typed shared state passed through LangGraph nodes
- **GraphRuntime** - Compiled LangGraph workflow used by FastAPI endpoints
- **FastAPIRoutes** - Backend API for session lifecycle and SSE graph interaction, includes DOCX export endpoint
- **PrismaChatAPI** - Frontend API routes that authenticate users and bridge to backend
- **VectorStore** - Chroma-based retrieval over pre-seeded standards/compliance corpus
- **MermaidValidation** - Syntax validation step used in graph post-processing
- **DocxExporter** - Converts Markdown to DOCX with formatted text, embedded diagram images, and metadata
- **DiagramRenderer** - Renders Mermaid diagrams to PNG via mmdc or mermaid.ink HTTP API
