import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
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
    },
  });

  if (!chat) {
    return NextResponse.json({ error: "Chat not found" }, { status: 404 });
  }

  const run = await getLatestNonTerminalRun(chat.id);
  return NextResponse.json({ run });
}
