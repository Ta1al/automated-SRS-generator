import bcrypt from "bcryptjs";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import {
  COOKIE_NAME,
  createSessionToken,
  getSessionCookieOptions,
} from "@/lib/auth";
import { readJsonBody, routeErrorResponse } from "@/lib/api-route";
import { prisma } from "@/lib/prisma";

const signupSchema = z.object({
  email: z.email(),
  password: z.string().min(8),
  name: z.string().min(1).max(100).optional(),
});

export async function POST(request: NextRequest) {
  try {
    const body = await readJsonBody(request);
    const parsed = signupSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json({ error: "Invalid signup payload." }, { status: 400 });
    }

    const { email, password, name } = parsed.data;

    const existing = await prisma.user.findUnique({ where: { email } });
    if (existing) {
      return NextResponse.json({ error: "Email already in use." }, { status: 409 });
    }

    const passwordHash = await bcrypt.hash(password, 12);
    const user = await prisma.user.create({
      data: {
        email,
        name,
        passwordHash,
      },
    });

    const token = await createSessionToken({ userId: user.id, email: user.email });
    const response = NextResponse.json({
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
      },
    });

    response.cookies.set(COOKIE_NAME, token, await getSessionCookieOptions());
    return response;
  } catch (error) {
    return routeErrorResponse(error, "Failed to sign up.");
  }
}
