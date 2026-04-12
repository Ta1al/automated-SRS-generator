# Frontend (Next.js)

This is the Next.js 16 frontend for the AI-Driven SRS Generator. It provides
a complete user interface for authentication, chat-based interaction with the
LangGraph backend, live SRS section previews, and document export.

## Features

- **Landing page** — Product pitch with hero section, feature cards, and CTA
  buttons ("Start a New SRS", "Open Workspace").
- **Login / Signup** — Email and password authentication with JWT session
  cookies (HS256, 7-day expiry, httpOnly, sameSite=lax).
- **Chat workspace** — Three-column layout:
  - **Left sidebar**: List of previous chats for the current user, sorted by
    last update. "New Chat" button creates a backend session and Prisma chat
    record.
  - **Center panel**: Active chat conversation with message history, text
    input, real-time node progress indicators, ETA estimation, and
    clarification question prompts (HITL interrupt handling).
  - **Right panel**: Live SRS section preview cards (6 sections: s1, s2,
    s3_iface, s3_fr, s3_nfr, s4), full Markdown document viewer, and export
    buttons (Markdown download, DOCX download). Supports targeted section
    revision mode — users can request edits to individual sections.
- **Dark/light theme toggle** — Persisted theme preference.

## Architecture

```
src/
├── app/
│   ├── page.tsx                          # Landing page
│   ├── login/page.tsx                    # Login form
│   ├── signup/page.tsx                   # Registration form
│   ├── chat/page.tsx                     # Protected workspace (auth-gated)
│   └── api/
│       ├── auth/
│       │   ├── signup/route.ts           # POST — register (bcrypt hash)
│       │   ├── login/route.ts            # POST — authenticate, set JWT cookie
│       │   ├── logout/route.ts           # POST — clear session cookie
│       │   └── me/route.ts              # GET — current user from JWT
│       └── chats/
│           ├── route.ts                  # GET (list) / POST (create)
│           └── [chatId]/
│               ├── route.ts             # GET / PUT / DELETE
│               ├── interact/route.ts    # POST — proxy to backend SSE
│               ├── messages/route.ts    # GET / POST
│               ├── runs/
│               │   └── active/
│               │       ├── route.ts     # GET — active ChatRun
│               │       └── stream/route.ts # GET — resume SSE
│               └── export/
│                   └── docx/route.ts    # GET — proxy DOCX download
├── components/
│   ├── chat-workspace.tsx               # Main 3-column workspace
│   └── theme-toggle.tsx                 # Dark/light toggle
└── lib/
    ├── auth.ts                          # JWT session (jose, HS256, 7d)
    ├── backend.ts                       # Backend fetch + SSE parser
    ├── chat-runner.ts                   # Run orchestration, stages, ETA
    ├── config.ts                        # Environment constants
    ├── http.ts                          # HTTP utilities
    ├── api-route.ts                     # API route helpers
    └── prisma.ts                        # Prisma client singleton
```

## Prerequisites

- Node.js 20+
- PostgreSQL running from root `docker-compose.yml`
- Backend API running at `http://localhost:8000`

## Environment

Copy `.env.example` to `.env` (already included with local defaults):

```bash
DATABASE_URL="postgresql://srs_user:srs_pass@localhost:5432/srs_db"
AUTH_SECRET="dev-local-secret-change-me"
BACKEND_API_URL="http://localhost:8000"
```

## Database setup

```bash
npm run prisma:generate
cd ..
docker compose exec -T postgres psql -U srs_user -d srs_db -f frontend/prisma/init_auth_chat.sql
```

This uses the same PostgreSQL instance as the backend, with additional tables
for users, chats, messages, runs, and stage timing stats managed via Prisma.

## Run

```bash
npm run dev
```

Open `http://localhost:3000`.

## Key libraries

| Package | Purpose |
|---|---|
| next | React framework with App Router |
| react-markdown + remark-gfm | Markdown rendering with GFM tables |
| mermaid | Client-side Mermaid diagram rendering |
| @prisma/client | PostgreSQL ORM |
| jose | JWT signing/verification |
| bcryptjs | Password hashing |
| zod | Runtime schema validation |
| tailwindcss | Utility-first CSS |
