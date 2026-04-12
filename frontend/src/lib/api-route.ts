import { NextRequest, NextResponse } from "next/server";
import { ZodError } from "zod";

import { extractHttpErrorMessage } from "@/lib/http";

export class ApiRouteError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ApiRouteError";
    this.status = status;
  }
}

export function apiError(message: string, status = 500) {
  return new ApiRouteError(message, status);
}

export async function readJsonBody(request: NextRequest) {
  try {
    return await request.json();
  } catch {
    throw apiError("Invalid JSON payload.", 400);
  }
}

export function routeErrorResponse(error: unknown, fallbackMessage: string) {
  if (error instanceof ApiRouteError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }

  if (error instanceof ZodError) {
    return NextResponse.json({ error: "Invalid request payload." }, { status: 400 });
  }

  if (error instanceof SyntaxError) {
    return NextResponse.json({ error: "Invalid JSON payload." }, { status: 400 });
  }

  if (error instanceof Error) {
    console.error(`[api-route] ${fallbackMessage}:`, error.message);
  } else {
    console.error(`[api-route] ${fallbackMessage}:`, error);
  }

  return NextResponse.json({ error: fallbackMessage }, { status: 500 });
}

export async function extractUpstreamError(response: Response, fallback: string) {
  return extractHttpErrorMessage(response, fallback);
}