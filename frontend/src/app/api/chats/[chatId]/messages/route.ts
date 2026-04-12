import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { routeErrorResponse } from "@/lib/api-route";
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
      include: {
        messages: {
          orderBy: {
            createdAt: "asc",
          },
        },
      },
    });

    if (!chat) {
      return NextResponse.json({ error: "Chat not found" }, { status: 404 });
    }

    return NextResponse.json({
      chat: {
        id: chat.id,
        title: chat.title,
        currentDocument: chat.currentDocument,
        stateJson: chat.stateJson,
        messages: chat.messages,
      },
    });
  } catch (error) {
    return routeErrorResponse(error, "Failed to load chat messages.");
  }
}
