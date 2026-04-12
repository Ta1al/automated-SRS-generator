import { NextResponse } from "next/server";

import { COOKIE_NAME } from "@/lib/auth";
import { routeErrorResponse } from "@/lib/api-route";

export async function POST() {
  try {
    const response = NextResponse.json({ ok: true });
    response.cookies.delete(COOKIE_NAME);
    return response;
  } catch (error) {
    return routeErrorResponse(error, "Failed to log out.");
  }
}
