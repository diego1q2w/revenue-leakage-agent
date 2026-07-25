import { test } from "node:test";
import assert from "node:assert/strict";
import { sendChatMessage, ChatRequestError } from "./api.ts";
import { resetMockCycle } from "./mock.ts";

test("sendChatMessage in mock mode returns canned responses and ignores fetch", async () => {
  resetMockCycle();
  let fetchCalled = false;
  const fakeFetch: typeof fetch = async () => {
    fetchCalled = true;
    throw new Error("fetch should not be called in mock mode");
  };

  const response = await sendChatMessage("thread-1", "hello", {
    mock: true,
    fetchImpl: fakeFetch,
  });

  assert.equal(fetchCalled, false);
  assert.equal(response.type, "message");
});

test("sendChatMessage in real mode posts thread_id and message to {apiUrl}/chat", async () => {
  let capturedUrl: string | undefined;
  let capturedInit: RequestInit | undefined;
  const fakeFetch: typeof fetch = async (url, init) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify({ type: "message", text: "hi" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const response = await sendChatMessage("thread-42", "are we leaking revenue?", {
    mock: false,
    apiUrl: "http://example.test",
    fetchImpl: fakeFetch,
  });

  assert.equal(capturedUrl, "http://example.test/chat");
  assert.equal(capturedInit?.method, "POST");
  assert.deepEqual(JSON.parse(String(capturedInit?.body)), {
    thread_id: "thread-42",
    message: "are we leaking revenue?",
  });
  assert.equal(response.type, "message");
  if (response.type === "message") {
    assert.equal(response.text, "hi");
  }
});

test("sendChatMessage throws ChatRequestError on a non-200 response", async () => {
  const fakeFetch: typeof fetch = async () =>
    new Response("Internal Server Error", { status: 500 });

  await assert.rejects(
    () =>
      sendChatMessage("thread-1", "hello", {
        mock: false,
        apiUrl: "http://example.test",
        fetchImpl: fakeFetch,
      }),
    ChatRequestError,
  );
});

test("sendChatMessage throws ChatRequestError when fetch rejects (network error)", async () => {
  const fakeFetch: typeof fetch = async () => {
    throw new TypeError("Failed to fetch");
  };

  await assert.rejects(
    () =>
      sendChatMessage("thread-1", "hello", {
        mock: false,
        apiUrl: "http://example.test",
        fetchImpl: fakeFetch,
      }),
    ChatRequestError,
  );
});

test("sendChatMessage defaults to mock mode when no config is passed and NEXT_PUBLIC_MOCK is unset", async () => {
  resetMockCycle();
  const previous = process.env.NEXT_PUBLIC_MOCK;
  delete process.env.NEXT_PUBLIC_MOCK;
  try {
    const response = await sendChatMessage("thread-1", "hello");
    // Mock mode never touches the network; a real fetch to a bogus host
    // would reject, so getting a well-typed response proves mock was used.
    assert.ok(response.type === "message" || response.type === "approval_request");
  } finally {
    if (previous === undefined) {
      delete process.env.NEXT_PUBLIC_MOCK;
    } else {
      process.env.NEXT_PUBLIC_MOCK = previous;
    }
  }
});
