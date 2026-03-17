# Entity-Relationship Diagram

This diagram shows the database schema and relationships for the system.

```mermaid
erDiagram
    USER ||--o{ CHAT : creates
    USER {
        string id PK
        string email UK
        string password
        datetime created_at
        datetime updated_at
    }

    CHAT ||--o{ MESSAGE : contains
    CHAT {
        string id PK
        string user_id FK
        string title
        datetime created_at
        datetime updated_at
    }

    MESSAGE {
        string id PK
        string chat_id FK
        string content
        string role
        datetime created_at
    }

    CHAT ||--o{ SRS_DOCUMENT : generates
    SRS_DOCUMENT {
        string id PK
        string chat_id FK
        string content
        string title
        datetime generated_at
        datetime updated_at
    }

    CHAT ||--o{ GENERATED_DIAGRAM : contains
    GENERATED_DIAGRAM {
        string id PK
        string chat_id FK
        string diagram_type
        string mermaid_code
        string description
        datetime created_at
    }

    SRS_DOCUMENT ||--o{ REQUIREMENT : includes
    REQUIREMENT {
        string id PK
        string srs_document_id FK
        string requirement_id
        string description
        string type
        string priority
    }

    USER ||--o{ SESSION : has
    SESSION {
        string id PK
        string user_id FK
        string token
        datetime created_at
        datetime expires_at
    }
```

## Entity Descriptions

### USER
- Primary entity representing system users
- Stores authentication credentials and metadata
- One-to-many relationship with CHAT and SESSION

### CHAT
- Represents a conversation/SRS generation session
- Links users to their conversations
- Contains multiple messages and generated documents

### MESSAGE
- Individual messages in a chat session
- Stores both user queries and system responses
- Includes role identifier (user/assistant)

### SRS_DOCUMENT
- Generated SRS documents
- References the chat that generated it
- Contains the complete SRS content

### GENERATED_DIAGRAM
- Mermaid diagrams generated during SRS creation
- Includes activity, class, data flow, and ER diagrams
- Stores actual Mermaid code and descriptions

### REQUIREMENT
- Individual requirements extracted from SRS
- Organized by type and priority
- Links back to parent SRS document

### SESSION
- Manages user authentication sessions
- Stores authentication tokens
- Tracks session expiration
