// A deliberately small Markdown parser covering the subset the agent actually
// emits: headings, bullet and numbered lists, paragraphs, bold, and inline
// code. It produces a plain data tree — components/Markdown.tsx turns that into
// React elements, so nothing here ever touches dangerouslySetInnerHTML.
//
// Underscore emphasis (_italic_) is deliberately NOT supported: the agent
// routinely writes identifiers like make_good_invoice and action_type, and
// treating those underscores as emphasis mangles them.

export type Span =
  | { type: "text"; text: string }
  | { type: "bold"; text: string }
  | { type: "italic"; text: string }
  | { type: "code"; text: string };

export type Block =
  | { type: "heading"; level: number; spans: Span[] }
  | { type: "paragraph"; lines: Span[][] }
  | { type: "list"; ordered: boolean; items: Span[][] };

const HEADING = /^(#{1,4})\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;

// **bold** first so it wins over *italic* at the same position; `code` is
// matched as a unit so its contents are never re-parsed for emphasis.
const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\n]+)\*/g;

/** Splits one line into styled spans. Unmatched text passes through verbatim. */
export function parseInline(text: string): Span[] {
  const spans: Span[] = [];
  let cursor = 0;

  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      spans.push({ type: "text", text: text.slice(cursor, start) });
    }

    const [, bold, code, italic] = match;
    if (bold !== undefined) spans.push({ type: "bold", text: bold });
    else if (code !== undefined) spans.push({ type: "code", text: code });
    else if (italic !== undefined) spans.push({ type: "italic", text: italic });

    cursor = start + match[0].length;
  }

  if (cursor < text.length) {
    spans.push({ type: "text", text: text.slice(cursor) });
  }
  return spans;
}

/** Parses assistant text into a flat list of blocks. Never throws: anything
 * unrecognized degrades to paragraph text, so odd output still renders. */
export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: Span[][] = [];
  let list: { ordered: boolean; items: Span[][] } | null = null;

  const flush = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: "paragraph", lines: paragraph });
      paragraph = [];
    }
    if (list) {
      blocks.push({ type: "list", ordered: list.ordered, items: list.items });
      list = null;
    }
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();

    if (line.trim() === "") {
      flush();
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flush();
      blocks.push({
        type: "heading",
        level: heading[1].length,
        spans: parseInline(heading[2]),
      });
      continue;
    }

    const bullet = BULLET.exec(line);
    const ordered = bullet ? null : ORDERED.exec(line);
    if (bullet || ordered) {
      const isOrdered = Boolean(ordered);
      const content = (bullet ?? ordered)![1];
      if (paragraph.length > 0) {
        blocks.push({ type: "paragraph", lines: paragraph });
        paragraph = [];
      }
      // A change of list kind starts a new list.
      if (list && list.ordered !== isOrdered) {
        blocks.push({ type: "list", ordered: list.ordered, items: list.items });
        list = null;
      }
      list ??= { ordered: isOrdered, items: [] };
      list.items.push(parseInline(content));
      continue;
    }

    // Plain prose line. A list in progress ends here.
    if (list) {
      blocks.push({ type: "list", ordered: list.ordered, items: list.items });
      list = null;
    }
    paragraph.push(parseInline(line));
  }

  flush();
  return blocks;
}
