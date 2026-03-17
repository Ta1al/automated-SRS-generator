# Frontend (Next.js)

This app provides:

- Landing page
- Login / signup
- Chat workspace with 3 columns:
	- Left: previous chats for the current user
	- Middle: active chat conversation
	- Right: current SRS state and document rendering

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

This uses the same PostgreSQL instance as the backend, with additional tables for users/chats/messages.

## Run

```bash
npm run dev
```

Open `http://localhost:3000`.
