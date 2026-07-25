import { test } from "node:test";
import assert from "node:assert/strict";
import { nextMockResponse, resetMockCycle, MOCK_DELAY_MS } from "./mock.ts";

test("mock cycle: 1st call returns the missing-September message", () => {
  resetMockCycle();
  const response = nextMockResponse();
  assert.equal(response.type, "message");
  assert.match(response.text, /September is missing/);
});

test("mock cycle: 2nd call returns an approval_request with a flat proposal", () => {
  resetMockCycle();
  nextMockResponse();
  const response = nextMockResponse();
  assert.equal(response.type, "approval_request");
  assert.match(response.text, /yes, apply it/i);
  assert.deepEqual(response.proposal, {
    action_type: "make_good_invoice",
    plan_id: "C-1001",
    amount: 8000,
    currency: "USD",
    reason: "Missing September 2025 billing",
  });
});

test("mock cycle: 3rd call returns the applied confirmation", () => {
  resetMockCycle();
  nextMockResponse();
  nextMockResponse();
  const response = nextMockResponse();
  assert.equal(response.type, "message");
  assert.match(response.text, /INV-MG-001/);
});

test("mock cycle: 4th call wraps back around to the 1st response", () => {
  resetMockCycle();
  nextMockResponse();
  nextMockResponse();
  nextMockResponse();
  const response = nextMockResponse();
  assert.equal(response.type, "message");
  assert.match(response.text, /September is missing/);
});

test("MOCK_DELAY_MS is approximately 600ms as specified", () => {
  assert.equal(MOCK_DELAY_MS, 600);
});
