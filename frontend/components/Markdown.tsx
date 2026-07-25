import { Fragment } from "react";
import { parseMarkdown, type Block, type Span } from "@/lib/markdown";

/** Renders the Markdown subset the agent emits as React elements. Text is
 * always rendered as text — no HTML is ever injected. */
export default function Markdown({ text }: { text: string }) {
  const blocks = parseMarkdown(text);

  return (
    <div className="flex flex-col gap-2">
      {blocks.map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </div>
  );
}

const HEADING_CLASS: Record<number, string> = {
  1: "text-base font-semibold",
  2: "text-sm font-semibold",
  3: "text-sm font-semibold",
  4: "text-xs font-semibold uppercase tracking-wide text-neutral-600",
};

function BlockView({ block }: { block: Block }) {
  if (block.type === "heading") {
    return (
      <p className={HEADING_CLASS[block.level] ?? HEADING_CLASS[4]}>
        <Spans spans={block.spans} />
      </p>
    );
  }

  if (block.type === "list") {
    const className = block.ordered
      ? "list-decimal space-y-1 pl-5"
      : "list-disc space-y-1 pl-5";
    const items = block.items.map((spans, i) => (
      <li key={i}>
        <Spans spans={spans} />
      </li>
    ));
    return block.ordered ? <ol className={className}>{items}</ol> : <ul className={className}>{items}</ul>;
  }

  return (
    <p>
      {block.lines.map((spans, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          <Spans spans={spans} />
        </Fragment>
      ))}
    </p>
  );
}

function Spans({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((span, i) => {
        if (span.type === "bold") return <strong key={i} className="font-semibold">{span.text}</strong>;
        if (span.type === "italic") return <em key={i}>{span.text}</em>;
        if (span.type === "code") {
          return (
            <code key={i} className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[0.85em]">
              {span.text}
            </code>
          );
        }
        return <Fragment key={i}>{span.text}</Fragment>;
      })}
    </>
  );
}
