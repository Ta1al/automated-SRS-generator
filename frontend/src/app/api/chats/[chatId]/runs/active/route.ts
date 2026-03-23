import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { getLatestNonTerminalRun } from "@/lib/chat-runner";
import { prisma } from "@/lib/prisma";

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

export async function GET(_request: NextRequest, context: Context) {
  const session = await getSessionUser();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { chatId } = await context.params;
  const chat = await prisma.chat.findFirst({
    where: {
      id: chatId,
      userId: session.userId,
    },
    select: {
      id: true,
      backendThreadId: true,
    },
  });

  if (!chat) {
    return NextResponse.json({ error: "Chat not found" }, { status: 404 });
  }

  const run = await getLatestNonTerminalRun(chat.id);
  const liveSections: Record<string, string> = {};

  if (run?.status === "RUNNING") {
    try {
      const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`, {
        cache: "no-store",
      });

      if (stateResponse.ok) {
        const statePayload = (await stateResponse.json()) as Record<string, unknown>;
        const sections = statePayload.sections;

        if (sections && typeof sections === "object" && !Array.isArray(sections)) {
          for (const [key, value] of Object.entries(sections as Record<string, unknown>)) {
            if (typeof value === "string") {
              const trimmed = value.trim();
              if (trimmed) {
                liveSections[key] = trimmed;
              }
            }
          }
        }
      }
    } catch {
    }
  }

  return NextResponse.json({
    run: run
      ? {
          ...run,
          liveSections,
        }
      : null,
  });
}
