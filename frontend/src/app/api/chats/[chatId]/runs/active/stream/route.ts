import { NextRequest } from "next/server";
import { ChatRunStatus } from "@prisma/client";

import { getSessionUser } from "@/lib/auth";
import { routeErrorResponse } from "@/lib/api-route";
import { backendFetch } from "@/lib/backend";
import { prisma } from "@/lib/prisma";

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

function toSseEvent(event: string, payload: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function normalizeSections(raw: unknown) {
  const sections: Record<string, string> = {};

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return sections;
  }

  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== "string") {
      continue;
    }

    const trimmed = value.trim();
    if (trimmed) {
      sections[key] = trimmed;
    }
  }

  return sections;
}

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function GET(request: NextRequest, context: Context) {
  let chat: { id: string; backendThreadId: string };
  try {
    const session = await getSessionUser();
    if (!session) {
      return new Response(toSseEvent("error", { message: "Unauthorized" }), {
        status: 401,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
        },
      });
    }

    const { chatId } = await context.params;
    const resolvedChat = await prisma.chat.findFirst({
      where: {
        id: chatId,
        userId: session.userId,
      },
      select: {
        id: true,
        backendThreadId: true,
      },
    });

    if (!resolvedChat) {
      return new Response(toSseEvent("error", { message: "Chat not found" }), {
        status: 404,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
        },
      });
    }

    chat = resolvedChat;
  } catch (error) {
    return routeErrorResponse(error, "Failed to initialize section stream.");
  }

  const encoder = new TextEncoder();
  let isClosed = false;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const writeEvent = (event: string, payload: unknown) => {
        if (isClosed) {
          return;
        }
        controller.enqueue(encoder.encode(toSseEvent(event, payload)));
      };

      const closeStream = () => {
        if (isClosed) {
          return;
        }
        isClosed = true;
        controller.close();
      };

      request.signal.addEventListener(
        "abort",
        () => {
          closeStream();
        },
        { once: true },
      );

      const runLoop = async () => {
        let lastSnapshot = "";

        while (!isClosed && !request.signal.aborted) {
          const chatStateRecord = await prisma.chat.findUnique({
            where: { id: chat.id },
            select: { stateJson: true },
          });

          const run = await prisma.chatRun.findFirst({
            where: {
              chatId: chat.id,
              status: {
                in: [ChatRunStatus.RUNNING, ChatRunStatus.NEEDS_INPUT],
              },
            },
            orderBy: {
              startedAt: "desc",
            },
            select: {
              status: true,
              currentNode: true,
              etaSeconds: true,
            },
          });

          if (!run) {
            writeEvent("done", {});
            closeStream();
            return;
          }

          let sections = normalizeSections(
            chatStateRecord?.stateJson &&
              typeof chatStateRecord.stateJson === "object" &&
              !Array.isArray(chatStateRecord.stateJson)
              ? (chatStateRecord.stateJson as Record<string, unknown>).live_sections
              : null,
          );

          let inferredCurrentNode: string | null = null;

          if (run.status === ChatRunStatus.RUNNING && (Object.keys(sections).length === 0 || !run.currentNode)) {
            try {
              const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`, {
                cache: "no-store",
              });

              if (stateResponse.ok) {
                const payload = (await stateResponse.json()) as Record<string, unknown>;
                sections = normalizeSections(payload.sections);
                const next = payload.next;
                if (Array.isArray(next) && next.length > 0 && typeof next[0] === "string") {
                  inferredCurrentNode = next[0];
                }
              }
            } catch {
            }
          }

          const snapshot = {
            status: run.status,
            currentNode: run.currentNode || inferredCurrentNode,
            etaSeconds: run.etaSeconds,
            sections,
          };
          const encodedSnapshot = JSON.stringify(snapshot);

          if (encodedSnapshot !== lastSnapshot) {
            writeEvent("sections", snapshot);
            lastSnapshot = encodedSnapshot;
          }

          await sleep(800);
        }

        closeStream();
      };

      runLoop().catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Failed to stream run sections.";
        writeEvent("error", { message });
        closeStream();
      });
    },
    cancel() {
      isClosed = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}