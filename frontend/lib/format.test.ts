import { test } from "node:test";
import assert from "node:assert/strict";
import { humanizeKey, formatProposalValue } from "./format.ts";

test("humanizeKey capitalizes a single word", () => {
  assert.equal(humanizeKey("amount"), "Amount");
});

test("humanizeKey converts snake_case to a capitalized phrase", () => {
  assert.equal(humanizeKey("action_type"), "Action type");
});

test("humanizeKey converts kebab-case to a capitalized phrase", () => {
  assert.equal(humanizeKey("plan-id"), "Plan id");
});

test("humanizeKey collapses repeated separators", () => {
  assert.equal(humanizeKey("plan__id"), "Plan id");
});

test("humanizeKey leaves an empty string unchanged", () => {
  assert.equal(humanizeKey(""), "");
});

test("formatProposalValue renders numbers and strings as-is", () => {
  assert.equal(formatProposalValue(10000), "10000");
  assert.equal(formatProposalValue("USD"), "USD");
});

test("formatProposalValue renders booleans as Yes/No", () => {
  assert.equal(formatProposalValue(true), "Yes");
  assert.equal(formatProposalValue(false), "No");
});

test("formatProposalValue renders null/undefined as an em dash", () => {
  assert.equal(formatProposalValue(null), "—");
  assert.equal(formatProposalValue(undefined), "—");
});
