// Rendering helpers for the generic proposal key-value card. The proposal
// object's keys vary by proposal and are never assumed ahead of time, so
// these functions must work on arbitrary snake_case/kebab-case keys and
// arbitrary JSON-primitive values.

/** "action_type" -> "Action type", "plan-id" -> "Plan id". */
export function humanizeKey(key: string): string {
  const words = key.split(/[_\-\s]+/).filter(Boolean);
  if (words.length === 0) return key;

  const [first, ...rest] = words;
  return [capitalize(first), ...rest.map((word) => word.toLowerCase())].join(" ");
}

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

/** Renders a proposal value for display. Booleans and nullish values get
 * friendlier text than String() would produce. */
export function formatProposalValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
