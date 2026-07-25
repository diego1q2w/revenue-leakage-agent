import { NextRequest, NextResponse } from "next/server";

/** Dedicated proxy for POST /backend/chat (long-running LLM calls). */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<NextResponse> {
  const target = `${BACKEND_URL}/chat`;
  console.info("[backend proxy] POST", target);

  try {
    const res = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
      },
      body: await request.text(),
    });

    console.info("[backend proxy] POST", target, "→", res.status);

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("[backend proxy] POST failed:", target, error);
    return NextResponse.json(
      {
        error: "backend_unreachable",
        message: String(error),
        hint: "Start the API with: make backend",
        target,
      },
      { status: 502 },
    );
  }
}
