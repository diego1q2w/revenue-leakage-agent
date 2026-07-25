# Frontend — Revenue Leakage Agent

Chat-only Next.js 16 (App Router) UI for the Revenue Leakage Agent. See the
[root README](../README.md) for the full project, architecture, and quickstart.

## Run

```sh
npm install
cp .env.example .env.local
npm run dev            # http://localhost:3000
```

The browser always talks to `/backend/*`, which the route handlers in
`app/backend/` proxy server-side to `BACKEND_URL` (default
`http://127.0.0.1:8000`). Set `NEXT_PUBLIC_MOCK=true` in `.env.local` to run the
UI against canned responses with no backend.

## Layout

| Path | Role |
|------|------|
| `components/Chat.tsx` | Chat container; one `thread_id` per page load |
| `components/MessageBubble.tsx` | Message rendering |
| `components/Markdown.tsx` | Renders the Markdown subset the agent emits |
| `components/ProposalCard.tsx` | Generic key-value card for approval requests |
| `lib/api.ts` | Single `sendChatMessage()`; mock/real toggle |
| `lib/types.ts` | Mirrors the backend `/chat` response contract |
| `app/backend/` | Server-side proxy to the FastAPI backend |

## Test

```sh
npm test               # node --test over lib/*.test.ts
npm run build
```
