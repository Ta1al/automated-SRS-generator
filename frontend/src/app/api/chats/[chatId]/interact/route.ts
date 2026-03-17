import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import type { InputJsonValue } from "@prisma/client/runtime/library";

import { getSessionUser } from "@/lib/auth";
import { backendFetch, consumeSseResponse } from "@/lib/backend";
import { prisma } from "@/lib/prisma";

const interactSchema = z.object({
  message: z.string().min(1),
  revisionTarget: z
    .object({
      title: z.string().min(1),
      content: z.string().min(1),
      sectionKey: z.string().min(1).optional(),
    })
    .optional(),
});

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

export async function POST(request: NextRequest, context: Context) {
  const session = await getSessionUser();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const parsed = interactSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid message" }, { status: 400 });
  }

  const { chatId } = await context.params;
  const chat = await prisma.chat.findFirst({
    where: {
      id: chatId,
      userId: session.userId,
    },
  });

  if (!chat) {
    return NextResponse.json({ error: "Chat not found" }, { status: 404 });
  }

  await prisma.chatMessage.create({
    data: {
      chatId: chat.id,
      role: "USER",
      content: parsed.data.message,
    },
  });

  const backendMessage = parsed.data.revisionTarget
    ? [
        "Revise the existing SRS draft section below.",
        `Target section: ${parsed.data.revisionTarget.title}`,
        parsed.data.revisionTarget.sectionKey
          ? `Section key: ${parsed.data.revisionTarget.sectionKey}`
          : "",
        "Current section text:",
        parsed.data.revisionTarget.content,
        "Requested change:",
        parsed.data.message,
        "Update the SRS consistently and preserve unaffected requirements unless the requested change requires broader edits.",
      ]
        .filter(Boolean)
        .join("\n\n")
    : parsed.data.message;

  const interactResponse = await backendFetch(
    `/api/sessions/${chat.backendThreadId}/interact`,
    {
      method: "POST",
      body: JSON.stringify({ message: backendMessage }),
    },
  );

  if (!interactResponse.ok) {
    const errorBody = await interactResponse.text();
    return NextResponse.json(
      {
        error: "Failed to interact with SRS backend.",
        details: errorBody,
      },
      { status: 502 },
    );
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      void (async () => {
        let errorAlreadySent = false;

        const sendEvent = (eventName: string, data: unknown) => {
          if (eventName === "error") {
            errorAlreadySent = true;
          }

          controller.enqueue(
            encoder.encode(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`),
          );
        };

        try {
          const { assistantMessage, finalDocument, questionPrompt, questions, statuses } =
            await consumeSseResponse(interactResponse, {
              onEvent: sendEvent,
            });

          if (assistantMessage) {
            await prisma.chatMessage.create({
              data: {
                chatId: chat.id,
                role: "ASSISTANT",
                content: assistantMessage,
              },
            });
          }

          let stateJsonForUpdate: InputJsonValue | undefined;
          if (chat.stateJson !== null && chat.stateJson !== undefined) {
            stateJsonForUpdate = chat.stateJson as InputJsonValue;
          }

          const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`);
          if (stateResponse.ok) {
            stateJsonForUpdate = (await stateResponse.json()) as InputJsonValue;
          }

          let currentDocument = finalDocument || chat.currentDocument;
          if (!currentDocument) {
            const documentResponse = await backendFetch(
              `/api/sessions/${chat.backendThreadId}/document`,
            );
            if (documentResponse.ok) {
              const documentPayload = await documentResponse.json();
              currentDocument = documentPayload.document ?? null;
            }
          }

          const nextTitle =
            chat.title === "New Chat" ? parsed.data.message.slice(0, 60) : chat.title;

          const chatUpdateData: {
            title: string;
            currentDocument: string | null;
            stateJson?: InputJsonValue;
          } = {
            title: nextTitle,
            currentDocument,
          };

          if (stateJsonForUpdate !== undefined) {
            chatUpdateData.stateJson = stateJsonForUpdate;
          }

          const updatedChat = await prisma.chat.update({
            where: { id: chat.id },
            data: chatUpdateData,
          });

          const messages = await prisma.chatMessage.findMany({
            where: { chatId: chat.id },
            orderBy: { createdAt: "asc" },
          });

          sendEvent("result", {
            chat: updatedChat,
            messages,
            questionPrompt,
            questions,
            statuses,
          });
        } catch (caughtError) {
          if (!errorAlreadySent) {
            sendEvent("error", {
              message:
                caughtError instanceof Error
                  ? caughtError.message
                  : "Failed to interact with SRS backend.",
            });
          }
        } finally {
          controller.close();
        }
      })();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
