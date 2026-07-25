"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { sendChatMessage, ChatRequestError } from "@/lib/api";
import type { ChatTurn } from "@/lib/types";
import MessageBubble from "@/components/MessageBubble";
import ThinkingIndicator from "@/components/ThinkingIndicator";

function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

const IS_MOCK_MODE = process.env.NEXT_PUBLIC_MOCK !== "false";

export default function Chat() {
  const [mounted, setMounted] = useState(false);
  // thread_id is created client-side only to avoid SSR/hydration mismatches.
  const [threadId, setThreadId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  useEffect(() => {
    setMounted(true);
    setThreadId(createId());
  }, []);

  useEffect(() => {
    if (!mounted || IS_MOCK_MODE) return;
    fetch("/backend/api/health")
      .then((res) => setBackendOk(res.ok))
      .catch(() => setBackendOk(false));
  }, [mounted]);

  const runSend = useCallback(
    async (text: string, replacingTurnId?: string) => {
      if (!threadId || sendingRef.current) return;

      sendingRef.current = true;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);

      try {
        const response = await sendChatMessage(threadId, text, {
          signal: controller.signal,
        });
        const assistantTurn: ChatTurn =
          response.type === "approval_request"
            ? { id: createId(), role: "assistant", text: response.text, proposal: response.proposal }
            : { id: createId(), role: "assistant", text: response.text };

        setTurns((prev) => [
          ...prev.filter((turn) => turn.id !== replacingTurnId),
          assistantTurn,
        ]);
      } catch (err) {
        if (err instanceof ChatRequestError && err.message === "Request cancelled.") {
          return;
        }
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        const message =
          err instanceof ChatRequestError ? err.message : "Something went wrong. Please try again.";
        const errorTurn: ChatTurn = { id: createId(), role: "error", text: message, retryText: text };

        setTurns((prev) => [...prev.filter((turn) => turn.id !== replacingTurnId), errorTurn]);
      } finally {
        sendingRef.current = false;
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setIsLoading(false);
      }
    },
    [threadId],
  );

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || isLoading || !threadId) return;

    setInput("");
    setTurns((prev) => [...prev, { id: createId(), role: "user", text }]);
    void runSend(text);
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    sendingRef.current = false;
    setIsLoading(false);
  };

  const handleRetry = useCallback(
    (turn: ChatTurn) => {
      if (turn.role !== "error" || isLoading || !threadId) return;
      void runSend(turn.retryText, turn.id);
    },
    [isLoading, runSend, threadId],
  );

  const canSend = Boolean(input.trim()) && !isLoading && Boolean(threadId);

  return (
    <div className="flex h-dvh flex-col bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white px-6 py-4">
        <h1 className="text-lg font-semibold text-neutral-900">Revenue Leakage Agent</h1>
        <p className="text-sm text-neutral-500">Ask about billing gaps in the sandbox ledger.</p>
        {mounted && IS_MOCK_MODE && (
          <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Mock mode is on — responses cycle from canned data, not the real agent. Set{" "}
            <code className="font-mono">NEXT_PUBLIC_MOCK=false</code> in{" "}
            <code className="font-mono">frontend/.env.local</code> and restart the dev server.
          </p>
        )}
        {mounted && !IS_MOCK_MODE && backendOk === false && (
          <p className="mt-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
            Backend not reachable. In a separate terminal run{" "}
            <code className="font-mono">make backend</code> from the project root, then refresh
            this page.
          </p>
        )}
        {mounted && !IS_MOCK_MODE && backendOk === true && (
          <p className="mt-1 text-xs text-green-700">Backend connected.</p>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {turns.length === 0 && (
            <p className="text-center text-sm text-neutral-400">
              Try: &ldquo;Any revenue leakage issues with plan C-1001?&rdquo;
            </p>
          )}
          {turns.map((turn) => (
            <MessageBubble key={turn.id} turn={turn} onRetry={handleRetry} />
          ))}
          {isLoading && <ThinkingIndicator />}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t border-neutral-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-2">
          {isLoading && (
            <p className="text-xs text-neutral-500">
              Waiting for the assistant (can take up to a minute while it calls tools)…{" "}
              <button
                type="button"
                onClick={handleCancel}
                className="font-medium text-neutral-700 underline hover:text-neutral-900"
              >
                Cancel
              </button>
            </p>
          )}
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about revenue leakage…"
              aria-label="Message"
              className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900"
            />
            <button
              type="submit"
              disabled={!canSend}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
