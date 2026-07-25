// Single integration point with the backend contract:
//   POST {API_URL}/chat  {"thread_id": "<uuid>", "message": "<user text>"}
// -> {"type": "message", "text": "..."} | {"type": "approval_request", ...}
//
// NEXT_PUBLIC_MOCK toggles between the canned mock (lib/mock.ts) and a real
// fetch. Both paths return the same ChatResponse type, so the rest of the
// app (Chat.tsx) exercises one rendering path regardless of mode — this is
// what lets switching to the real backend require zero code changes.
import type { ChatRequest, ChatResponse } from "./types.ts";
import { getMockResponse } from "./mock.ts";

/** Thrown for any failure to get a usable response: network failure,
 * non-200 status, or a malformed body. The message is safe to show directly
 * in an error bubble — no internal details leak through it. */
export class ChatRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatRequestError";
  }
}

export interface ChatClientConfig {
  mock: boolean;
  apiUrl: string;
  fetchImpl: typeof fetch;
  signal?: AbortSignal;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 120_000;

function combineSignals(userSignal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeoutSignal =
    typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(timeoutMs)
      : undefined;

  if (userSignal && timeoutSignal && typeof AbortSignal.any === "function") {
    return AbortSignal.any([userSignal, timeoutSignal]);
  }
  if (userSignal) return userSignal;
  if (timeoutSignal) return timeoutSignal;

  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);
  return controller.signal;
}

function defaultConfig(): ChatClientConfig {
  return {
    mock: process.env.NEXT_PUBLIC_MOCK !== "false",
    // Always use the same-origin proxy; never call :8000 directly from the browser.
    apiUrl: "/backend",
    // fetch must be bound — bare `fetch` throws "Illegal invocation" in browsers.
    fetchImpl: globalThis.fetch.bind(globalThis),
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };
}

export async function sendChatMessage(
  threadId: string,
  message: string,
  configOverrides: Partial<ChatClientConfig> = {},
): Promise<ChatResponse> {
  const config = { ...defaultConfig(), ...configOverrides };

  if (config.mock) {
    return getMockResponse();
  }

  const body: ChatRequest = { thread_id: threadId, message };
  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const signal = combineSignals(config.signal, timeoutMs);

  let res: Response;
  try {
    res = await config.fetchImpl(`${config.apiUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      if (config.signal?.aborted) {
        throw new ChatRequestError("Request cancelled.");
      }
      throw new ChatRequestError(
        `The assistant took longer than ${Math.round(timeoutMs / 1000)}s. The backend may still be working — check its terminal, then retry.`,
      );
    }
    const detail = err instanceof Error ? err.message : String(err);
    throw new ChatRequestError(
      `Could not reach the assistant (${detail}). Is the backend running? Start it with: make backend`,
    );
  }

  if (!res.ok) {
    if (res.status === 502) {
      try {
        const payload = (await res.json()) as { hint?: string; message?: string };
        throw new ChatRequestError(
          payload.hint ?? payload.message ?? "Backend not reachable from the Next.js proxy.",
        );
      } catch (parseErr) {
        if (parseErr instanceof ChatRequestError) throw parseErr;
      }
    }
    throw new ChatRequestError(`The assistant returned an error (status ${res.status}). Retry?`);
  }

  try {
    return (await res.json()) as ChatResponse;
  } catch {
    throw new ChatRequestError("The assistant sent back a response we couldn't understand.");
  }
}
