// Lightweight "assistant is thinking" indicator shown while a request is
// in flight. The only animation in the app, per the style spec.
export default function ThinkingIndicator() {
  return (
    <div className="flex justify-start" aria-live="polite" aria-label="Assistant is thinking">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-neutral-200 bg-white px-4 py-3 shadow-sm">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400" />
        <span className="ml-2 text-xs text-neutral-500">Thinking…</span>
      </div>
    </div>
  );
}
