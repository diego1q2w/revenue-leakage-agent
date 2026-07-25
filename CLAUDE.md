# CLAUDE.md — Revenue Leakage Agent

Guide for AI assistants (Claude, Cursor, etc.) working in this repository.

## What this project is

A conversational AI agent that acts as a **financial detective**: it compares
billing plans to issued invoices, finds revenue leakage, proposes corrective
actions, and applies them to a **writable sandbox** only after human approval.

The repo exists to demonstrate two things: a genuine ReAct loop (the model is
the router, nothing is scripted) and a write gate enforced by graph structure
rather than by prompt instructions. Changes that blur either of those defeat
the purpose — see the hard constraints below.

## Hard constraints (do not break)

1. **Frozen frontend contract** — `POST /chat` response shapes in
   `backend/app/api/schemas.py` and `frontend/lib/types.ts` must stay exactly:
   - `{"type": "message", "text": "..."}`
   - `{"type": "approval_request", "text": "...", "proposal": {flat kv object}}`
   - Chat mounts at `/chat` (no `/api` prefix). Do not add approve/reject
     buttons or special resume fields to the frontend.

2. **Structural write gate** — sandbox writes must go through
   `graph.py` → `_gated_apply()` → `interrupt()` before `apply_action` executes.
   Never bypass this with a direct `SandboxLedger.apply()` call from the agent
   node or API layer. Prompt-only "ask permission" is not sufficient.

3. **Exactly 8 tools** — the design fixes these and only these:
   `load_plan`, `query_invoices`, `fx_convert`, `propose_make_good_invoice`,
   `propose_credit_memo`, `propose_plan_amendment`, `apply_action`,
   `rollback_action`. Do not add a 9th tool — enrich existing tools instead
   (e.g. credit memos are embedded in `query_invoices` results).

4. **Investigate → propose → apply flow** — an investigation turn reports
   findings and asks whether to draft a fix; it must not call `propose_*`.
   Only once the user asks for the fix does the model call `propose_*` (which
   just drafts into `sandbox/proposals.json`) followed immediately by
   `apply_action`, which is the only tool that writes ledgers and is gated.
   Two confirmations, two purposes: the prose question authorizes proposing,
   the gate authorizes the write.

5. **Read-only `/data`** — never mutate files under `data/`. All writes go to
   `sandbox/`.

6. **Tests must not touch real sandbox** — use the `tmp_sandbox` fixture in
   `backend/tests/conftest.py` for any test that writes.

## Architecture

```
frontend/          Chat UI → POST /chat
    ↓
backend/app/api/   FastAPI routes (chat at root, sandbox under /api)
    ↓
backend/app/agent/ AgentService → LangGraph (agent ↔ tools loop)
    ↓
backend/app/data/  Repositories (read) + ProposalStore + SandboxLedger (write)
    ↓
data/              Immutable seed JSON
sandbox/           Writable ledgers + proposals + audit log
```

### Agent graph (`backend/app/agent/graph.py`)

Two nodes, one conditional edge:

- **agent** — single LLM call with all 8 tools bound; responds with prose or
  tool calls.
- **tools** — `tools_node()` executes tool calls; `apply_action` is sorted
  first so the interrupt fires before any other side effect in the batch.
- **route_after_agent** — tool calls → tools; prose → END.

State channels (`backend/app/agent/state.py`):

| Channel | Purpose |
|---------|---------|
| `messages` | Full conversation + tool results (checkpointer restores across turns) |
| `pending_proposal` | Single slot; set by `propose_*`, cleared on apply/decline |
| `applied_actions` | Append-only list for rollback / "what did you apply?" |

Do **not** add `active_plan_id` or `findings` channels — context lives in
message history.

### AgentService (`backend/app/agent/service.py`)

Bridges API ↔ graph. Critical behavior:

- If thread has a pending `interrupt` (write gate parked), every incoming
  message is passed as `Command(resume=message)`. Only the exact phrase
  `yes, apply it` (case/punctuation insensitive) applies; **anything else**
  declines, clears `pending_proposal`, and the graph loops back to the agent
  to respond to the user.
- If graph ends parked at interrupt, return `approval_request` to frontend.
- Otherwise return `message` with extracted assistant text.

Stateful memory: `build_graph` compiles with `MemorySaver`; every invoke uses
`config={"configurable": {"thread_id": thread_id}}` so conversation history
and tool results persist per chat session.

### Data runtime (`backend/app/data/runtime.py`)

Single `get_runtime()` cache used by **tools** and **sandbox API routes**.
Always resolve repos/ledger through this — do not construct separate
`SandboxLedger` instances in routes.

After changing `DATA_DIR` or `SANDBOX_DIR` in tests:

```python
get_settings.cache_clear()
get_runtime.cache_clear()
```

## Tool ↔ data mapping

| Tool | Data layer | Notes |
|------|------------|-------|
| `load_plan` | `PlanRepository.get()` | Returns error + `known_plan_ids` if missing |
| `query_invoices` | `InvoiceRepository.query()` + `CreditMemoRepository` | Each invoice includes `credit_memos[]`; supports `invoice_id` filter |
| `fx_convert` | `ExchangeRateRepository.convert()` | Identity, exact date, on-or-before, inverse pair |
| `propose_*` | `ProposalStore.create()` | Never writes ledgers |
| `apply_action` | `ProposalStore.get()` + `SandboxLedger.apply()` | Gated in graph, not in tool body alone |
| `rollback_action` | `SandboxLedger.rollback()` | Flags row, appends audit entry |

Tool docstrings in `backend/app/agent/tools.py` are the **model-facing
descriptions** — keep them accurate and example-rich when editing.

## Seeded data (investigation scenarios)

| Id | Scenario |
|----|----------|
| `C-1001` | Monthly $8k USD; September 2025 invoice missing |
| `C-1007` / `C-1007-A1` | Amendment plan (`amends` field) |
| `I-9123` | 25k EUR invoice; FX converts to 27k USD vs 25k target; memo M-300 exists |
| `I-9202` | Orphan invoice (empty `plan_id`) |
| `C-1010` | Annual plan; upgrade amendment scenario |

## Frontend (`frontend/`)

- **Entry**: `components/Chat.tsx` — one `thread_id` per page load.
- **API client**: `lib/api.ts` — single `sendChatMessage()`; mock toggle via
  `NEXT_PUBLIC_MOCK`.
- **Rendering**: `MessageBubble.tsx`, `ProposalCard.tsx` (generic kv rows).
- **No** state-management libraries, no streaming, no auth.

Frontend-specific Next.js notes: see `frontend/AGENTS.md`.

## Commands

```sh
make install          # deps
make dev              # backend + frontend
make test             # backend pytest
make reset-sandbox    # empty sandbox/*.json
cd frontend && npm test && npm run build
```

Run verification before claiming work is done:

```sh
pytest backend/tests -q
cd frontend && npm test
```

Live LLM integration test (needs `ANTHROPIC_API_KEY`):

```sh
pytest backend/tests/test_agent_tools.py::test_agent_detects_missing_invoice -v
```

Fast CI (skip integration):

```sh
pytest backend/tests -m "not integration" -q
```

## Code conventions

- **Python**: match existing style — minimal abstractions, rich docstrings on
  public/tool surfaces, recoverable error dicts from tools (don't raise into the
  graph for expected failures like unknown plan id).
- **TypeScript**: plain React state + fetch; types in `lib/types.ts` mirror the
  frozen contract exactly.
- **Commits**: only when the user asks.
- **Scope**: don't refactor unrelated code; don't add features beyond what's
  asked. This is a focused demo, not a product.

## Common pitfalls

| Pitfall | Correct approach |
|---------|------------------|
| Frontend sends resume flag | Never — `AgentService` detects parked interrupt |
| `apply_action` writes without gate | Only `_gated_apply` in graph calls the tool after interrupt |
| Tests write to `./sandbox` | Use `tmp_sandbox` fixture |
| Stale runtime after env change | `get_runtime.cache_clear()` |
| Adding 9th tool for credit memos | Embed memos in `query_invoices` results |
| Mutating `data/` | Read-only; use `sandbox/` |
| Changing chat response shapes | Frozen — update both backend schemas and frontend types together only if architect explicitly unfreezes |

## Key files

| File | Role |
|------|------|
| `backend/app/agent/graph.py` | ReAct graph + write gate |
| `backend/app/agent/tools.py` | 8 LangChain tools |
| `backend/app/agent/prompts.py` | System prompt (domain rules) |
| `backend/app/agent/service.py` | API ↔ graph bridge |
| `backend/app/data/runtime.py` | Shared data-layer handles |
| `backend/app/data/sandbox.py` | Apply, rollback, audit, reset |
| `backend/app/api/routes/chat.py` | POST /chat |
| `frontend/lib/api.ts` | Frontend ↔ backend contract |
| `backend/tests/conftest.py` | `client`, `tmp_sandbox` fixtures |
| `backend/tests/test_agent_graph.py` | Write gate tests (no LLM) |

## When extending

- **New read capability**: extend an existing repository + existing read tool.
- **New write capability**: new `propose_*` + ledger routing in `SandboxLedger`;
  gate still goes through `apply_action`.
- **New API endpoint**: add under `backend/app/api/routes/`, schema in
  `schemas.py`, test in `test_api.py`.
- **UI changes**: keep chat-only; no new pages unless explicitly requested.
