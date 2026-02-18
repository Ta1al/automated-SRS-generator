import { NextResponse } from "next/server";

export async function POST(req) {
  return NextResponse.json({ content: "SRS generation backend has been removed." });
}
