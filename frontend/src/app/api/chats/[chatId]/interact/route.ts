import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { z } from "zod";

import { getSessionUser } from "@/lib/auth";
import { readJsonBody, routeErrorResponse } from "@/lib/api-route";
import {
  getRunSummary,
  startBackgroundChatRun,
} from "@/lib/chat-runner";
import { prisma } from "@/lib/prisma";

const interactSchema = z.object({
  message: z.string().min(1),
  generateDiagrams: z.boolean().optional(),
  diagramsOnly: z.boolean().optional(),
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

function formatStoredUserMessage(message: string, revisionTarget?: { title: string }) {
  if (!revisionTarget?.title) {
    return message;
  }

  return `[Selected section: ${revisionTarget.title}]\n${message}`;
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const session = await getSessionUser();
    if (!session) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await readJsonBody(request);
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

    const existingRun = await prisma.chatRun.findFirst({
      where: {
        chatId: chat.id,
        status: "RUNNING",
      },
      orderBy: {
        startedAt: "desc",
      },
      select: {
        id: true,
      },
    });

    if (existingRun) {
      const run = await getRunSummary(existingRun.id);
      return NextResponse.json(
        {
          error: "A generation run is already in progress for this chat.",
          run,
        },
        { status: 409 },
      );
    }

    await prisma.chatMessage.create({
      data: {
        chatId: chat.id,
        role: "USER",
        content: formatStoredUserMessage(parsed.data.message, parsed.data.revisionTarget),
      },
    });

    const initialRunData: {
      chatId: string;
      inputMessage: string;
      revisionTarget?: Prisma.InputJsonValue;
    } = {
      chatId: chat.id,
      inputMessage: parsed.data.message,
    };

    if (parsed.data.revisionTarget) {
      initialRunData.revisionTarget = parsed.data.revisionTarget as Prisma.InputJsonValue;
    }

    const run = await prisma.chatRun.create({
      data: initialRunData,
    });

    void startBackgroundChatRun({
      runId: run.id,
      chatId: chat.id,
      message: parsed.data.message,
      revisionTarget: parsed.data.revisionTarget,
      generateDiagrams: parsed.data.generateDiagrams,
      diagramsOnly: parsed.data.diagramsOnly,
    });

    const runSummary = await getRunSummary(run.id);

    return NextResponse.json({
      run: runSummary,
    });
  } catch (error) {
    return routeErrorResponse(error, "Failed to start chat generation.");
  }
}
