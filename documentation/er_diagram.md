# Entity-Relationship Diagram

This diagram reflects the implemented Prisma schema used by the frontend app.

```mermaid
erDiagram
    USER ||--o{ CHAT : creates
    USER {
        string id PK
        string email UK
        string name
        string password_hash
        datetime created_at
        datetime updated_at
    }

    CHAT ||--o{ CHAT_MESSAGE : contains
    CHAT {
        string id PK
        string user_id FK
        string title
        string backend_thread_id UK
        string current_document
        json state_json
        datetime created_at
        datetime updated_at
    }

    CHAT_MESSAGE {
        string id PK
        string chat_id FK
        enum role "USER|ASSISTANT"
        string content
        datetime created_at
    }
```

## Entity Descriptions

### USER
- Primary entity representing system users
- Stores authentication credentials and metadata
- One-to-many relationship with CHAT

### CHAT
- Represents a user conversation tied to a backend thread
- Links users to their conversations
- Contains multiple messages and stores latest generated document/state snapshot

### CHAT_MESSAGE
- Individual messages in a chat session
- Stores both user queries and system responses
- Includes role as enum (`USER` or `ASSISTANT`)
