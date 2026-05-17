# Entity-Relationship Diagram

This diagram reflects the implemented Prisma schema used by the frontend app (`frontend/prisma/schema.prisma`). All five models are shown with their relationships, primary keys, unique constraints, and foreign keys.

```mermaid
erDiagram
    USER ||--o{ CHAT : creates
    USER {
        string id PK "CUID"
        string email UK
        string name "nullable"
        string password_hash
        datetime created_at
        datetime updated_at
    }

    CHAT ||--o{ CHAT_MESSAGE : contains
    CHAT ||--o{ CHAT_RUN : tracks
    CHAT {
        string id PK "CUID"
        string user_id FK "CASCADE delete"
        string title
        string backend_thread_id UK "links to backend session UUID"
        string current_document "nullable"
        json state_json "nullable, JSONB"
        datetime created_at
        datetime updated_at
    }

    CHAT_MESSAGE {
        string id PK "CUID"
        string chat_id FK "CASCADE delete"
        enum role "USER or ASSISTANT"
        string content
        datetime created_at
    }

    CHAT_RUN {
        string id PK "CUID"
        string chat_id FK "CASCADE delete"
        enum status "RUNNING|COMPLETED|FAILED|NEEDS_INPUT"
        string input_message
        json revision_target "nullable, JSONB"
        string current_node "nullable"
        datetime current_node_started "nullable"
        json status_events "nullable, JSONB"
        string question_prompt "nullable"
        json questions_json "nullable, JSONB"
        int eta_seconds "nullable"
        string error_message "nullable"
        datetime started_at
        datetime completed_at "nullable"
        datetime created_at
        datetime updated_at
    }

    STAGE_TIMING_STAT {
        string node PK "graph node name"
        int sample_count "default 0"
        float avg_duration_ms "default 0"
        datetime created_at
        datetime updated_at
    }
```

## Entity Descriptions

### USER
- Primary entity representing authenticated system users.
- Stores email (unique), optional display name, and bcrypt password hash.
- One-to-many relationship with CHAT - deleting a user cascades to all their chats.

### CHAT
- Represents a user conversation tied to a backend LangGraph session.
- `backendThreadId` (unique) links to the backend's session UUID used for graph checkpointing.
- Stores the latest generated document (`currentDocument`) and a JSONB snapshot of the LangGraph state (`stateJson`) for the right-panel section preview.
- One-to-many relationships with CHAT_MESSAGE and CHAT_RUN.
- Indexed on `(userId, updatedAt)` for efficient chat list queries.

### CHAT_MESSAGE
- Individual messages exchanged in a chat session.
- Role is an enum: `USER` (human input) or `ASSISTANT` (AI response).
- Indexed on `(chatId, createdAt)` for chronological retrieval.

### CHAT_RUN
- Tracks the execution state of a single graph invocation within a chat.
- Status lifecycle: `RUNNING` → `COMPLETED` | `FAILED` | `NEEDS_INPUT`.
- Records the currently executing graph node, SSE status events (JSONB), clarification questions, ETA estimate, and any error message.
- `revisionTarget` (JSONB) stores metadata when the run is a section revision.
- Indexed on `(chatId, startedAt DESC)` and `(chatId, status)` for efficient active-run lookups.

### STAGE_TIMING_STAT
- Singleton-per-node table tracking average execution duration across all runs (EMA-based).
- Used by the frontend ETA estimation logic in `chat-runner.ts`.
- `node` is the primary key (e.g. `"draft_section_1"`, `"ingest_and_map_domain"`).

## Indexes

| Table | Index | Columns | Purpose |
|---|---|---|---|
| CHAT | `@@index([userId, updatedAt])` | userId, updatedAt | Fast chat list per user |
| CHAT_MESSAGE | `@@index([chatId, createdAt])` | chatId, createdAt | Chronological message retrieval |
| CHAT_RUN | `@@index([chatId, startedAt(sort: Desc)])` | chatId, startedAt DESC | Latest runs first |
| CHAT_RUN | `@@index([chatId, status])` | chatId, status | Find active runs by chat |

## Relationships

| Parent | Child | Type | Foreign Key | On Delete |
|---|---|---|---|---|
| User | Chat | 1:N | userId | Cascade |
| Chat | ChatMessage | 1:N | chatId | Cascade |
| Chat | ChatRun | 1:N | chatId | Cascade |
