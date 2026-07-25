import { test } from "node:test";
import assert from "node:assert/strict";
import { parseInline, parseMarkdown } from "./markdown.ts";

test("parseInline returns a single text span for plain prose", () => {
  assert.deepEqual(parseInline("no markup here"), [{ type: "text", text: "no markup here" }]);
});

test("parseInline extracts bold runs and keeps surrounding text", () => {
  assert.deepEqual(parseInline("Applied **INV-MG-001** today"), [
    { type: "text", text: "Applied " },
    { type: "bold", text: "INV-MG-001" },
    { type: "text", text: " today" },
  ]);
});

test("parseInline extracts inline code", () => {
  assert.deepEqual(parseInline("type `yes, apply it`"), [
    { type: "text", text: "type " },
    { type: "code", text: "yes, apply it" },
  ]);
});

test("parseInline treats a single asterisk pair as italic", () => {
  assert.deepEqual(parseInline("*emphasis*"), [{ type: "italic", text: "emphasis" }]);
});

test("parseInline leaves snake_case identifiers untouched", () => {
  // The agent writes these constantly; underscore emphasis would mangle them.
  assert.deepEqual(parseInline("action_type is make_good_invoice"), [
    { type: "text", text: "action_type is make_good_invoice" },
  ]);
});

test("parseInline does not re-parse emphasis inside code", () => {
  assert.deepEqual(parseInline("`a **b** c`"), [{ type: "code", text: "a **b** c" }]);
});

test("parseMarkdown reads a heading and its level", () => {
  const blocks = parseMarkdown("## Findings: Plan C-1001");
  assert.equal(blocks.length, 1);
  assert.deepEqual(blocks[0], {
    type: "heading",
    level: 2,
    spans: [{ type: "text", text: "Findings: Plan C-1001" }],
  });
});

test("parseMarkdown groups consecutive bullets into one list", () => {
  const blocks = parseMarkdown("- first\n- second\n- third");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "list");
  assert.equal(blocks[0].type === "list" && blocks[0].ordered, false);
  assert.equal(blocks[0].type === "list" && blocks[0].items.length, 3);
});

test("parseMarkdown recognizes numbered lists as ordered", () => {
  const blocks = parseMarkdown("1. one\n2. two");
  assert.equal(blocks[0].type === "list" && blocks[0].ordered, true);
});

test("parseMarkdown starts a new list when the kind changes", () => {
  const blocks = parseMarkdown("- bullet\n1. numbered");
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type === "list" && blocks[0].ordered, false);
  assert.equal(blocks[1].type === "list" && blocks[1].ordered, true);
});

test("parseMarkdown splits paragraphs on blank lines", () => {
  const blocks = parseMarkdown("first para\n\nsecond para");
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type, "paragraph");
  assert.equal(blocks[1].type, "paragraph");
});

test("parseMarkdown keeps single newlines as separate lines in one paragraph", () => {
  const blocks = parseMarkdown("line one\nline two");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type === "paragraph" && blocks[0].lines.length, 2);
});

test("parseMarkdown returns no blocks for empty text", () => {
  assert.deepEqual(parseMarkdown(""), []);
});

test("parseMarkdown handles a realistic assistant reply", () => {
  const reply = [
    "## Findings: Plan C-1001 (ACME Corp)",
    "",
    "**Plan terms:** 12-month monthly SaaS, 96,000 USD total.",
    "",
    "- Jan-Aug invoiced at 8,000 USD",
    "- September missing",
    "",
    "Would you like me to draft that make-good invoice?",
  ].join("\n");

  const kinds = parseMarkdown(reply).map((b) => b.type);
  assert.deepEqual(kinds, ["heading", "paragraph", "list", "paragraph"]);
});
