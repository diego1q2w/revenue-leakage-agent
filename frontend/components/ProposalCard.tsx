import { humanizeKey, formatProposalValue } from "@/lib/format";
import type { ProposalObject } from "@/lib/types";

/** Renders an arbitrary flat proposal object as generic key-value rows.
 * Keys vary by proposal and are never assumed ahead of time — this
 * component makes no assumptions beyond "flat object of primitives". */
export default function ProposalCard({ proposal }: { proposal: ProposalObject }) {
  const entries = Object.entries(proposal);
  if (entries.length === 0) return null;

  return (
    <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
        Proposed action
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {entries.map(([key, value]) => (
          <div className="contents" key={key}>
            <dt className="font-medium text-amber-900">{humanizeKey(key)}</dt>
            <dd className="text-amber-950">{formatProposalValue(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
