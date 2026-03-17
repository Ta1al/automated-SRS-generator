# Class Diagram

This diagram shows the main classes and their relationships in the system.

```mermaid
classDiagram
    class User {
        +id: string
        +email: string
        +password: string
        +createdAt: datetime
        +login()
        +logout()
        +signup()
    }

    class Chat {
        +id: string
        +userId: string
        +title: string
        +createdAt: datetime
        +updatedAt: datetime
        +getMessages()
        +addMessage()
    }

    class Message {
        +id: string
        +chatId: string
        +content: string
        +role: string
        +createdAt: datetime
    }

    class Graph {
        +state: GraphState
        +nodes: list
        +edges: list
        +compile()
        +invoke()
    }

    class GraphState {
        +documents: list
        +query: string
        +requirements: list
        +srs: string
    }

    class VectorStore {
        +embeddings: list
        +documents: list
        +addDocuments()
        +similaritySearch()
    }

    class SRSGenerator {
        +graph: Graph
        +vectorStore: VectorStore
        +generateSRS()
        +validateSRS()
    }

    class MermaidValidator {
        +validateDiagram()
        +validateSyntax()
    }

    User "1" -- "*" Chat: has
    Chat "1" -- "*" Message: contains
    SRSGenerator "1" -- "1" Graph: uses
    SRSGenerator "1" -- "1" VectorStore: uses
    SRSGenerator "1" -- "1" MermaidValidator: uses
    Graph "1" -- "1" GraphState: maintains
```

## Class Descriptions

- **User** - Represents system users with authentication
- **Chat** - Represents a chat session for SRS generation
- **Message** - Individual messages within a chat
- **Graph** - LangGraph workflow for SRS generation
- **GraphState** - State management for the graph
- **VectorStore** - Manages document embeddings and retrieval
- **SRSGenerator** - Main orchestrator for SRS generation
- **MermaidValidator** - Validates generated Mermaid diagrams
