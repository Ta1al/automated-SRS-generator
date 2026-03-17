import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";

import { appConfig } from "@/lib/config";

const COOKIE_NAME = "srs_auth";
const encoder = new TextEncoder();
const authSecret = encoder.encode(appConfig.authSecret);

type SessionPayload = {
  userId: string;
  email: string;
};

export async function createSessionToken(payload: SessionPayload) {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(authSecret);
}

export async function verifySessionToken(token: string) {
  const { payload } = await jwtVerify(token, authSecret);
  return payload as SessionPayload;
}

export async function getSessionUser() {
  const cookieStore = await cookies();
  const token = cookieStore.get(COOKIE_NAME)?.value;

  if (!token) {
    return null;
  }

  try {
    const payload = await verifySessionToken(token);
    return {
      userId: payload.userId,
      email: payload.email,
    };
  } catch {
    return null;
  }
}

export async function getSessionCookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  };
}

export { COOKIE_NAME };
