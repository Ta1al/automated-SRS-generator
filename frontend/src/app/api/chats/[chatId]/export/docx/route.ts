import { NextRequest, NextResponse } from "next/server";

import { getSessionUser } from "@/lib/auth";
import { extractUpstreamError, routeErrorResponse } from "@/lib/api-route";
import { appConfig } from "@/lib/config";
import { prisma } from "@/lib/prisma";

type Context = {
  params: Promise<{
    chatId: string;
  }>;
};

function buildFileName(title: string | null | undefined) {
  const safeTitle = (title || "srs-document")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);

  return `${safeTitle || "srs-document"}.docx`;
}

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
        backendThreadId: true,
        title: true,
      },
    });

    if (!chat) {
      return NextResponse.json({ error: "Chat not found" }, { status: 404 });
    }

    const backendResponse = await fetch(
      `${appConfig.backendApiUrl}/api/sessions/${chat.backendThreadId}/document.docx`,
      {
        method: "GET",
        cache: "no-store",
        headers: {
          Accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      },
    );

    const contentType = backendResponse.headers.get("content-type") || "";

    if (
      !backendResponse.ok ||
      backendResponse.status !== 200 ||
      !contentType.includes(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      )
    ) {
      const detail = await extractUpstreamError(backendResponse, "Failed to export DOCX.");

      return NextResponse.json({ error: detail }, { status: backendResponse.status });
    }

    const fileName = buildFileName(chat.title);
    const bytes = await backendResponse.arrayBuffer();

    return new Response(bytes, {
      status: 200,
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": `attachment; filename="${fileName}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return routeErrorResponse(error, "Failed to export DOCX.");
  }
}
