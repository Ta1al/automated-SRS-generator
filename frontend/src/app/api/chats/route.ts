import { NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { extractUpstreamError, routeErrorResponse } from "@/lib/api-route";
import { backendFetch } from "@/lib/backend";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
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
  } catch (error) {
    return routeErrorResponse(error, "Failed to load chats.");
  }
}

export async function POST() {
  try {
    const session = await getSessionUser();
    if (!session) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const backendResponse = await backendFetch("/api/sessions", {
      method: "POST",
    });

    if (!backendResponse.ok) {
      const errorMessage = await extractUpstreamError(
        backendResponse,
        "Failed to create backend session.",
      );

      return NextResponse.json(
        { error: errorMessage },
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
  } catch (error) {
    return routeErrorResponse(error, "Failed to create chat.");
  }
}
