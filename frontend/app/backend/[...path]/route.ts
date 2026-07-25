import { NextRequest, NextResponse } from "next/server";

/** Server-side proxy: browser → /backend/* → FastAPI on :8000.
 * More reliable than next.config rewrites alone for POST /chat. */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

async function proxy(request: NextRequest, path: string[]): Promise<NextResponse> {
  const target = `${BACKEND_URL}/${path.join("/")}${request.nextUrl.search}`;
  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  console.info("[backend proxy]", request.method, target);

  try {
    const res = await fetch(target, {
      method: request.method,
      headers: {
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
      },
      body: hasBody ? await request.text() : undefined,
    });

    console.info("[backend proxy]", request.method, target, "→", res.status);

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("[backend proxy] failed:", target, error);
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

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}
