# Revenue Leakage Agent

[![CI](https://github.com/diego1q2w/revenue-leakage-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/diego1q2w/revenue-leakage-agent/actions/workflows/ci.yml)

A conversational AI agent that acts as a **financial detective**: it compares
billing plans against issued invoices, finds revenue leakage, proposes
corrective actions (make-good invoice, credit memo, plan amendment), and writes
them to a sandbox **only after a human approves**.

The point of the repo is the agent architecture, not the billing domain. Two
things are worth reading:

- **A real ReAct loop** — one LLM node bound to eight tools, looping
  agent ↔ tools until it produces prose. Nothing scripts which tool runs when;
  the model plans each step from context. No chains, no router, no workflow DAG.
- **A structural write gate** — the approval step is enforced by the graph, not
  by the prompt. `apply_action` is intercepted in `graph.py` and parked on a
  LangGraph `interrupt()` before any write executes. A jailbroken or confused
  model physically cannot write to the ledger without a human resume.

<!-- Screenshot: run `NEXT_PUBLIC_MOCK=true npm run dev` in frontend/, send three
     messages to get bubble → proposal card → bubble, save the capture as
     docs/screenshot.png, then uncomment the line below.
![Chat UI showing an investigation and an approval request](docs/screenshot.png)
-->

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, LangGraph, LangChain (Python 3.12, `uv`) |
| Model | Anthropic Claude Sonnet 5 (`claude-sonnet-5`) |
| Frontend | Next.js 16, TypeScript, Tailwind (App Router) |
| Config | python-dotenv (root `.env`) + `frontend/.env.local` |

## Layout

```
backend/app/api/       FastAPI routes + Pydantic schemas
backend/app/data/      Read-only repos over /data, writable sandbox ledger
backend/app/agent/     LangGraph graph, 8 tools, prompts, AgentService
backend/tests/         pytest suite (71 tests)
frontend/              Chat-only Next.js UI
data/                  Read-only seed data (plans, invoices, memos, FX rates)
sandbox/               Writable ledgers, proposals, audit log (gitignored)
CLAUDE.md              Guide for AI assistants working in this repo
```

## Quickstart

```sh
cp .env.example .env                     # set ANTHROPIC_API_KEY
cp frontend/.env.example frontend/.env.local
make install                             # uv sync + npm install
make dev                                 # backend :8000, frontend :3000
```

Open http://localhost:3000.

```sh
make test                                # backend pytest (71 tests)
cd frontend && npm test                  # frontend tests (18 tests)
make reset-sandbox                       # wipe sandbox ledgers + proposals
make help                                # all make targets
```

No API key handy? Set `NEXT_PUBLIC_MOCK=true` in `frontend/.env.local` and run
only the frontend — the UI renders canned responses through the exact same code
path as the real backend.

## Environment

**Root `.env`** (backend):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | — | Required for live agent |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Claude model id |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Frontend origins (both — browsers treat them as different) |
| `DATA_DIR` | `./data` | Read-only datasets |
| `SANDBOX_DIR` | `./sandbox` | Writable ledgers |
| `LOG_LEVEL` | `INFO` | Agent loop traces (`agent.flow` logger in uvicorn terminal) |

**`frontend/.env.local`** (frontend):

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_MOCK` | `false` | `true` = canned UI responses, no backend |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Where the Next.js proxy forwards `/backend/*` (server-side only) |

## How the loop works

```
        ┌──────────────────────────────────┐
        │              agent               │  one LLM call, 8 tools bound
        └───────────┬──────────────────────┘
      tool calls    │    prose
        ┌───────────┘        └────────► END
        ▼
  ┌───────────┐   apply_action?  ┌───────────────────┐
  │   tools   │ ───────────────► │  interrupt()      │ ◄── human types
  └─────┬─────┘                  │  write gate       │     "yes, apply it"
        │                        └─────────┬─────────┘
        └────────────◄─────────────────────┘
```

Opening turn of `"any revenue leakage on plan C-1001?"`:

1. `agent` emits `load_plan("C-1001")` + `query_invoices({plan_id: "C-1001"})`
   in one batch → `tools`
2. `tools` appends the plan JSON ($8k/month USD) and nine invoices → `agent`
3. `agent` has both sides of the diff, needs nothing more → prose: *"September
   is missing, $8,000 in missed revenue"* → END

The follow-up `"what currency is that plan in?"` is a fresh invoke on the same
`thread_id`. The checkpointer restores prior messages — including the plan JSON
from step 2 — so the model answers with zero tool calls. That is why there is no
`active_plan_id` state channel: cross-turn context already lives in the message
history.

Tool calls batch within an iteration when they are independent. Iteration count
is the depth of the data-dependency chain, not the number of tools — `fx_convert`
can't batch with `load_plan` because its arguments come from the fetch results.

**The 8 tools:** `load_plan`, `query_invoices`, `fx_convert`,
`propose_make_good_invoice`, `propose_credit_memo`, `propose_plan_amendment`,
`apply_action`, `rollback_action`. Docstrings in
`backend/app/agent/tools.py` are the model-facing descriptions.

**State channels:** `messages` (checkpointed), `pending_proposal` (single slot,
one proposal in flight), `applied_actions` (append-only, powers rollback).

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/chat` | Send message to agent |
| `GET` | `/chat/{thread_id}/history` | Thread message history |
| `GET` | `/api/sandbox` | Current sandbox ledger contents |
| `GET` | `/api/sandbox/audit-log` | Applied / rolled-back actions |
| `POST` | `/api/sandbox/reset` | Reset sandbox to empty state |

### Chat contract

```http
POST /chat
{"thread_id": "<uuid>", "message": "<user text>"}
```

Response is exactly one of:

```json
{"type": "message", "text": "<assistant reply>"}
```

```json
{"type": "approval_request", "text": "<confirmation question>",
 "proposal": {<flat key-value object>}}
```

Approval and rejection are ordinary chat messages — the frontend sends no
approve/reject flag and knows nothing about the gate. The backend `AgentService`
detects that a thread is parked at an `interrupt()` and routes the next message
in as a graph resume. Only the exact phrase `yes, apply it` applies; anything
else discards the proposal and loops back to the agent for a reply.

## Try it

| Prompt | What it exercises |
|--------|-------------------|
| *"Any revenue leakage issues with plan C-1001?"* | Missing September 2025 invoice ($8k/month) |
| *"Was invoice I-9123 billed correctly?"* | EUR→USD FX overbilling; existing credit memo M-300 |
| *"What currency is that plan in?"* (follow-up) | Checkpointer restores context, no tool calls |

Reply `yes, apply it` to a proposal to write it to the sandbox. Inspect with
`curl http://localhost:8000/api/sandbox`, undo with `make reset-sandbox`.

## Tests

```sh
make test                                       # all backend tests
pytest backend/tests -m "not integration" -q    # fast run, no API key needed
pytest backend/tests -m integration -v          # live LLM tests only
cd frontend && npm test
```

Backend tests never write to the real `./sandbox` — the `tmp_sandbox` fixture
redirects `SANDBOX_DIR` to a temp directory. CI runs everything except the
integration tests, which need a live `ANTHROPIC_API_KEY`.

## Notes

The seed data under `data/` is synthetic. This is a demo: there is no auth, no
persistence beyond flat JSON files, and the checkpointer is in-memory
(`MemorySaver`), so conversations reset when the backend restarts. Don't point
it at anything real.

## License

MIT — see [LICENSE](LICENSE).
