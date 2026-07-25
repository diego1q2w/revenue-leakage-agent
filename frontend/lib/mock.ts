// Mock backend used when NEXT_PUBLIC_MOCK=true (see api.ts). Cycles through
// the three canned responses from the frozen spec, in order, forever. This
// module owns only the canned data and delay; api.ts decides when to use it
// so the real fetch path and the mock path share one rendering contract.
import type { ChatResponse } from "./types.ts";

export const MOCK_DELAY_MS = 600;

const MOCK_RESPONSES: readonly ChatResponse[] = [
  {
    type: "message",
    text: "Plan C-1001 bills $8,000 monthly (USD). Invoices run Jan–Aug and Oct 2025; September is missing — $8,000 in missed revenue.",
  },
  {
    type: "approval_request",
    text: 'Would you like me to apply this to the sandbox? Type exactly "yes, apply it" to confirm — anything else declines.',
    proposal: {
      action_type: "make_good_invoice",
      plan_id: "C-1001",
      amount: 8000,
      currency: "USD",
      reason: "Missing September 2025 billing",
    },
  },
  {
    type: "message",
    text: "Applied to sandbox: INV-MG-001.",
  },
];

let callCount = 0;

/** Returns the next canned response in the cycle. Exported (alongside
 * resetMockCycle) so unit tests can assert on the sequence deterministically. */
export function nextMockResponse(): ChatResponse {
  const response = MOCK_RESPONSES[callCount % MOCK_RESPONSES.length];
  callCount += 1;
  return response;
}

/** Test-only hook: rewinds the cycle so each test starts from response #1. */
export function resetMockCycle(): void {
  callCount = 0;
}

/** Simulates network latency, then returns the next canned response. */
export async function getMockResponse(): Promise<ChatResponse> {
  await delay(MOCK_DELAY_MS);
  return nextMockResponse();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
