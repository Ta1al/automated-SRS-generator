DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'MessageRole') THEN
    CREATE TYPE "MessageRole" AS ENUM ('USER', 'ASSISTANT');
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ChatRunStatus') THEN
    CREATE TYPE "ChatRunStatus" AS ENUM ('RUNNING', 'COMPLETED', 'FAILED', 'NEEDS_INPUT');
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS "User" (
  "id" TEXT PRIMARY KEY,
  "email" TEXT NOT NULL UNIQUE,
  "name" TEXT,
  "passwordHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "Chat" (
  "id" TEXT PRIMARY KEY,
  "userId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "backendThreadId" TEXT NOT NULL UNIQUE,
  "currentDocument" TEXT,
  "stateJson" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Chat_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "Chat_userId_updatedAt_idx" ON "Chat"("userId", "updatedAt");

CREATE TABLE IF NOT EXISTS "ChatMessage" (
  "id" TEXT PRIMARY KEY,
  "chatId" TEXT NOT NULL,
  "role" "MessageRole" NOT NULL,
  "content" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ChatMessage_chatId_fkey" FOREIGN KEY ("chatId") REFERENCES "Chat"("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "ChatMessage_chatId_createdAt_idx" ON "ChatMessage"("chatId", "createdAt");

CREATE TABLE IF NOT EXISTS "ChatRun" (
  "id" TEXT PRIMARY KEY,
  "chatId" TEXT NOT NULL,
  "status" "ChatRunStatus" NOT NULL DEFAULT 'RUNNING',
  "inputMessage" TEXT NOT NULL,
  "revisionTarget" JSONB,
  "currentNode" TEXT,
  "currentNodeStarted" TIMESTAMP(3),
  "statusEvents" JSONB,
  "questionPrompt" TEXT,
  "questionsJson" JSONB,
  "etaSeconds" INTEGER,
  "errorMessage" TEXT,
  "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "completedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ChatRun_chatId_fkey" FOREIGN KEY ("chatId") REFERENCES "Chat"("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "ChatRun_chatId_startedAt_idx" ON "ChatRun"("chatId", "startedAt" DESC);
CREATE INDEX IF NOT EXISTS "ChatRun_chatId_status_idx" ON "ChatRun"("chatId", "status");

CREATE TABLE IF NOT EXISTS "StageTimingStat" (
  "node" TEXT PRIMARY KEY,
  "sampleCount" INTEGER NOT NULL DEFAULT 0,
  "avgDurationMs" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
