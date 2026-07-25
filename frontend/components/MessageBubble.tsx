import type { ChatTurn } from "@/lib/types";
import ProposalCard from "@/components/ProposalCard";

/** Renders one turn of the conversation. User bubbles are right-aligned;
 * assistant and error bubbles are left-aligned. Markdown-ish assistant text
 * is rendered as plain text with preserved line breaks (whitespace-pre-wrap),
 * per spec. */
export default function MessageBubble({
  turn,
  onRetry,
}: {
  turn: ChatTurn;
  onRetry: (turn: ChatTurn) => void;
}) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-neutral-900 px-4 py-2 text-sm text-white">
          {turn.text}
        </div>
      </div>
    );
  }

  if (turn.role === "error") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[80%] rounded-2xl rounded-bl-sm border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          <p className="whitespace-pre-wrap">{turn.text}</p>
          <button
            type="button"
            onClick={() => onRetry(turn)}
            className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-2xl rounded-bl-sm border border-neutral-200 bg-white px-4 py-2 text-sm text-neutral-900 shadow-sm">
        <p className="whitespace-pre-wrap">{turn.text}</p>
        {turn.proposal && (
          <>
            <ProposalCard proposal={turn.proposal} />
            <p className="mt-3 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-600">
              To apply, type{" "}
              <span className="font-medium text-neutral-800">yes, apply it</span> exactly and
              press Send. Any other reply declines and discards this proposal.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
