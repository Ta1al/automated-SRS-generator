import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { routeErrorResponse } from "@/lib/api-route";
import { backendFetch } from "@/lib/backend";
import { getLatestNonTerminalRun } from "@/lib/chat-runner";
import { prisma } from "@/lib/prisma";

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

export async function GET(_request: NextRequest, context: Context) {
  try {
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
        title: true,
        stateJson: true,
      },
    });

    if (!chat) {
      return NextResponse.json({ error: "Chat not found" }, { status: 404 });
    }

    const run = await getLatestNonTerminalRun(chat.id);
    const liveSections: Record<string, string> = {};
    let inferredCurrentNode: string | null = null;

    if (run?.status === "RUNNING") {
      const liveSectionsFromState =
        chat.stateJson &&
        typeof chat.stateJson === "object" &&
        !Array.isArray(chat.stateJson) &&
        (chat.stateJson as Record<string, unknown>).live_sections &&
        typeof (chat.stateJson as Record<string, unknown>).live_sections === "object" &&
        !Array.isArray((chat.stateJson as Record<string, unknown>).live_sections)
          ? ((chat.stateJson as Record<string, unknown>).live_sections as Record<string, unknown>)
          : null;

      if (liveSectionsFromState) {
        for (const [key, value] of Object.entries(liveSectionsFromState)) {
          if (typeof value === "string") {
            const trimmed = value.trim();
            if (trimmed) {
              liveSections[key] = trimmed;
            }
          }
        }
      }

      if (Object.keys(liveSections).length === 0 || !run.currentNode) {
        try {
          const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`, {
            cache: "no-store",
          });

          if (stateResponse.ok) {
            const statePayload = (await stateResponse.json()) as Record<string, unknown>;
            const sections = statePayload.sections;
            const next = statePayload.next;

            if (Array.isArray(next) && next.length > 0 && typeof next[0] === "string") {
              inferredCurrentNode = next[0];
            }

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
    }

    return NextResponse.json({
      run: run
        ? {
            ...run,
            currentNode: run.currentNode || inferredCurrentNode,
            chatTitle: chat.title,
            liveSections,
          }
        : null,
    });
  } catch (error) {
    return routeErrorResponse(error, "Failed to load active run status.");
  }
}
