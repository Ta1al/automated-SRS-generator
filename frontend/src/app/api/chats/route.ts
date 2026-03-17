import { NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getSessionUser();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const chats = await prisma.chat.findMany({
    where: { userId: session.userId },
    orderBy: { updatedAt: "desc" },
    include: {
      _count: {
        select: {
          messages: true,
        },
      },
    },
  });

  return NextResponse.json({ chats });
}

export async function POST() {
  const session = await getSessionUser();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const backendResponse = await backendFetch("/api/sessions", {
    method: "POST",
  });

  if (!backendResponse.ok) {
    return NextResponse.json(
      { error: "Failed to create backend session." },
      { status: 502 },
    );
  }

  const data = await backendResponse.json();
  const threadId = data.thread_id as string;

  const chat = await prisma.chat.create({
    data: {
      userId: session.userId,
      title: "New Chat",
      backendThreadId: threadId,
    },
  });

  return NextResponse.json({ chat }, { status: 201 });
}
