import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { routeErrorResponse } from "@/lib/api-route";
import { backendFetch } from "@/lib/backend";
import { prisma } from "@/lib/prisma";

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

export async function DELETE(_request: NextRequest, context: Context) {
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
      },
    });

    if (!chat) {
      return NextResponse.json({ error: "Chat not found" }, { status: 404 });
    }

    try {
      await backendFetch(`/api/sessions/${chat.backendThreadId}`, {
        method: "DELETE",
      });
    } catch {
    }

    await prisma.chat.delete({
      where: {
        id: chat.id,
      },
    });

    return NextResponse.json({ ok: true });
  } catch (error) {
    return routeErrorResponse(error, "Failed to delete chat.");
  }
}