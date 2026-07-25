"""LangChain tools exposed to the Revenue Leakage Agent.

The tool surface is fixed at eight: three read tools over the immutable ./data
files, three propose_* tools that create action drafts, and apply/rollback
which are the only tools that write to the ./sandbox ledgers.

Corrective actions follow a strict propose -> human approval -> apply flow:
propose_* never writes to the sandbox, and apply_action must only be called
after the user has explicitly approved the proposal in the conversation.

Docstrings double as the tool descriptions sent to the model, so they spell
out when to call each tool and include worked examples.
"""

from types import SimpleNamespace
from typing import Any

from langchain_core.tools import tool

from backend.app.data.runtime import get_runtime


def _runtime() -> SimpleNamespace:
    """Alias kept for tests that clear the cached runtime via tools module."""
    return get_runtime()


@tool
def load_plan(plan_id: str) -> dict[str, Any]:
    """Load the full details of one billing plan by its exact plan_id.

    Call this first whenever the user names a plan, or before judging whether
    a plan's invoices match what was contracted. The record contains
    total_value, currency, cadence ("Monthly" | "Quarterly" | "Annual"),
    start_date, entitlements, free-text notes, and — on amendment plans — an
    "amends" field naming the plan it supersedes.

    Examples:
    - "Any leakage on plan C-1001?" -> load_plan("C-1001"), then
      query_invoices(plan_id="C-1001") and compare expected per-period amount
      (total_value / periods, or the notes' stated target) against what was
      actually invoiced.
    - load_plan("C-1007") whose notes mention it is superseded ->
      also load_plan("C-1007-A1") and use the amendment's terms for periods
      after its start_date.

    Args:
        plan_id: Exact plan identifier, e.g. "C-1001" or "C-1007-A1".

    Returns the plan as a JSON object; if the id is unknown, returns an error
    object that includes the list of known plan ids so you can recover.
    """
    rt = _runtime()
    plan = rt.plans.get(plan_id)
    if plan is None:
        known_ids = [p.plan_id for p in rt.plans.list_all()]
        return {
            "error": f"No billing plan with plan_id '{plan_id}'.",
            "known_plan_ids": known_ids,
        }
    return plan.model_dump()


@tool
def query_invoices(
    plan_id: str | None = None,
    customer_name: str | None = None,
    invoice_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """Search issued invoices. All filters are optional and combine with AND.

    Use this to see what was actually billed, then compare against the plan's
    expected schedule to spot leakage: missing periods, wrong amounts, wrong
    currency, or orphan invoices. Each returned invoice includes a
    `credit_memos` list of any existing adjustments already issued against it
    (from data/credit_memos.json) so you can see whether part of a discrepancy
    was already corrected before proposing another. Note: some invoices may
    have an empty plan_id (payments with no contract reference) — query by
    customer_name to surface those.

    Examples:
    - Find gaps: query_invoices(plan_id="C-1001") -> a Monthly plan with
      invoices for Jan..Aug and Oct but nothing issued in September is a
      missed billing period.
    - Investigate one invoice: query_invoices(invoice_id="I-9123") -> the
      EUR invoice plus any credit memos already on file (M-300 may already
      cover part of an FX overbilling).
    - Cross-check a customer: query_invoices(customer_name="Globex Ltd")
      returns invoices across all their plans, including any with an empty
      plan_id (orphans).
    - Scope by time: query_invoices(plan_id="C-1010", date_from="2025-01-01",
      date_to="2025-06-30") for H1 only.

    Args:
        plan_id: Exact plan id to filter on, e.g. "C-1001".
        customer_name: Exact customer name, e.g. "ACME Corp".
        invoice_id: Exact invoice id, e.g. "I-9123".
        date_from: Inclusive lower bound on issue_date (ISO date, "2025-01-01").
        date_to: Inclusive upper bound on issue_date (ISO date, "2025-12-31").

    Returns a JSON list of invoices, each with invoice_id, plan_id,
    customer_name, issue_date, due_date, amount_invoiced, currency, status,
    description, and credit_memos (list, possibly empty). An empty list means
    nothing matched the filters.
    """
    rt = _runtime()
    invoices = rt.invoices.query(
        plan_id=plan_id,
        customer_name=customer_name,
        invoice_id=invoice_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows: list[dict[str, Any]] = []
    for invoice in invoices:
        row = invoice.model_dump()
        row["credit_memos"] = [
            memo.model_dump() for memo in rt.credit_memos.list_for_invoice(invoice.invoice_id)
        ]
        rows.append(row)
    return rows


@tool
def fx_convert(amount: float, from_ccy: str, to_ccy: str, on_date: str) -> dict[str, Any]:
    """Convert a monetary amount between currencies using the FX rate table.

    Call this whenever amounts are in different currencies before comparing
    them — never eyeball currency math. The typical leakage case: an invoice
    was issued in EUR against a USD-denominated plan, so the numerically equal
    amount is actually an overbilling once converted.

    Examples:
    - Invoice I-9123 bills 25000 EUR on 2025-09-12 but the plan target is
      25000 USD -> fx_convert(25000, "EUR", "USD", "2025-09-12") -> 27000 USD,
      i.e. a 2000 USD overbilling worth a credit memo.
    - Same-currency calls are identity: fx_convert(100, "USD", "USD", ...) -> 100.

    Args:
        amount: The amount to convert.
        from_ccy: ISO currency code the amount is in, e.g. "EUR".
        to_ccy: ISO currency code to convert to, e.g. "USD".
        on_date: Date of the transaction (ISO date, e.g. "2025-09-12") — the
            rate effective on or nearest before this date is used.

    Returns the converted amount plus the inputs used; returns an error object
    if no rate exists for the currency pair.
    """
    rt = _runtime()
    try:
        converted = rt.fx.convert(amount, from_ccy, to_ccy, on_date)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "amount": amount,
        "from_ccy": from_ccy,
        "to_ccy": to_ccy,
        "on_date": on_date,
        "converted_amount": converted,
    }


@tool
def propose_make_good_invoice(plan_id: str, amount: float, reason: str) -> dict[str, Any]:
    """Draft a make-good invoice to recover missed or underbilled revenue.

    Use when a billing period was never invoiced, or was invoiced below the
    plan's contracted amount. This only creates a proposal draft — nothing is
    written to the sandbox.

    When NOT to call: the investigation turn itself. Reporting a discrepancy
    and drafting its fix are separate turns — describe what you found, ask
    whether to draft the fix, and only call this once the user says yes. Also
    never on informational follow-ups ("what currency?", "explain that").

    Once the user has asked for the fix, call this and immediately follow with
    apply_action using the returned proposal_id — applying surfaces the
    confirmation question to the user; nothing is written until they approve.

    Examples:
    - Plan C-1001 bills 8000 USD monthly and September 2025 has no invoice ->
      propose_make_good_invoice("C-1001", 8000, "Missing September 2025
      billing period; plan bills 8000 USD/month").
    - A quarter was invoiced 20000 against a 22500 target ->
      propose_make_good_invoice(plan_id, 2500, "Underbilled Q2 by 2500 USD").

    Args:
        plan_id: The plan the recovered revenue belongs to.
        amount: Amount to invoice, in the plan's own currency.
        reason: Evidence-based justification citing the periods and numbers.

    Returns the created proposal (including its proposal_id) as a JSON object.
    """
    rt = _runtime()
    draft = rt.proposals.create(
        action_type="make_good_invoice",
        payload={"plan_id": plan_id, "amount": amount},
        reason=reason,
    )
    return draft.model_dump()


@tool
def propose_credit_memo(invoice_id: str, amount: float, reason: str) -> dict[str, Any]:
    """Draft a credit memo against a specific invoice to correct overbilling.

    Use when a customer was billed more than the plan allows — a pricing
    error, duplicate billing, or a currency mismatch that inflated the amount.
    This only creates a proposal draft.

    When NOT to call: the investigation turn itself — report the overbilling
    and ask whether to draft the credit memo first. Also never on informational
    follow-ups about data already in the thread.

    Once the user has asked for the fix, call this and immediately follow with
    apply_action using the returned proposal_id — the user is asked to confirm
    there before anything is written.

    Examples:
    - Invoice I-9123 for 25000 EUR converts to 27000 USD against a 25000 USD
      target -> propose_credit_memo("I-9123", 2000, "FX overbilling: 25000 EUR
      = 27000 USD vs 25000 USD contracted; crediting the 2000 USD excess").
      (Check existing credit memos first — a partial adjustment may already
      exist for the same invoice.)

    Args:
        invoice_id: The overbilled invoice, e.g. "I-9123".
        amount: Credit amount (positive number) in the invoice's currency
            context — state the currency reasoning in `reason`.
        reason: Evidence-based justification with the calculation.

    Returns the created proposal (including its proposal_id) as a JSON object.
    """
    rt = _runtime()
    draft = rt.proposals.create(
        action_type="credit_memo",
        payload={"invoice_id": invoice_id, "amount": amount},
        reason=reason,
    )
    return draft.model_dump()


@tool
def propose_plan_amendment(
    plan_id: str, change_set: dict[str, Any], reason: str
) -> dict[str, Any]:
    """Draft an update to a billing plan's contracted terms.

    Use when the agreement itself should change — not for one-off billing
    corrections (use make-good invoices or credit memos for those). Typical
    triggers: the customer upgraded, entitlements changed, or the recorded
    plan no longer reflects the real agreement (e.g. an amendment exists on
    paper but not in the billing system).

    When NOT to call: the investigation turn itself — describe the mismatch and
    ask whether to draft the amendment first. Also never when the user is only
    asking about plan details already loaded in this thread.

    Once the user has asked for the amendment, call this and immediately follow with
    apply_action using the returned proposal_id.

    Examples:
    - Upgrade: propose_plan_amendment("C-1010", {"total_value": 130000,
      "entitlements": ["Analytics", "Consulting", "Premium Support"]},
      "Customer upgraded to premium tier; contract value increased").
    - Cadence fix: propose_plan_amendment("C-1007", {"cadence": "Quarterly",
      "total_value": 100000}, "Agreement renegotiated from annual to quarterly").

    Args:
        plan_id: The plan to amend.
        change_set: Only the fields to change, with their new values (e.g.
            total_value, cadence, entitlements, notes).
        reason: Evidence-based justification for the amendment.

    Returns the created proposal (including its proposal_id) as a JSON object.
    """
    rt = _runtime()
    draft = rt.proposals.create(
        action_type="plan_amendment",
        payload={"plan_id": plan_id, "change_set": change_set},
        reason=reason,
    )
    return draft.model_dump()


@tool
def apply_action(proposal_id: str) -> dict[str, Any]:
    """Apply a proposed action to the writable sandbox — the human approval
    gate lives inside this tool.

    Call ONLY immediately after a propose_* tool, in a turn where the user has
    asked you to carry out the fix. Do NOT call on the investigation turn that
    merely reports a discrepancy, and not on informational follow-ups (e.g.
    "what currency is that plan?") — those are answered in plain text from
    conversation context with zero write-path tool calls.

    Calling apply_action does NOT write anything by itself: execution pauses,
    the user is shown the exact proposal and asked to confirm (reply yes/no),
    and the write happens only if they approve.

    Read the result faithfully:
    - An action_id (e.g. "INV-MG-001") means the user approved and the write
      happened — report that id back to them.
    - A declined result means the user did not approve and NOTHING was
      written — acknowledge and continue; re-propose only if they actually
      wanted changes.

    Example flow:
    1. propose_make_good_invoice(...) -> proposal_id "PR-001"
    2. apply_action("PR-001") -> [user is asked to confirm here]
    3. Result has action_id "INV-MG-001" -> tell the user it was applied.

    Args:
        proposal_id: The id returned by the propose_* tool.

    Returns the applied action (with its action_id and the ledger record), a
    declined marker, or an error object if the proposal doesn't exist or was
    already applied.
    """
    rt = _runtime()
    draft = rt.proposals.get(proposal_id)
    if draft is None:
        return {"error": f"No proposal with id '{proposal_id}'. Propose an action first."}
    try:
        applied = rt.sandbox.apply(draft)
    except ValueError as exc:
        return {"error": str(exc)}
    return applied.model_dump()


@tool
def rollback_action(action_id: str) -> dict[str, Any]:
    """Undo a previously applied sandbox action.

    Use when the user asks to revert something that was applied ("undo that",
    "roll back the credit memo") or when an applied action turns out to be
    based on a wrong calculation. The record is flagged as rolled back (the
    ledger keeps history) and the rollback is added to the audit log.

    Example:
    - User: "Actually, undo that make-good invoice." -> rollback_action with
      the action_id reported when it was applied, then confirm to the user.

    Args:
        action_id: The id of the applied action (returned by apply_action).

    Returns the rolled-back action as a JSON object; returns an error object
    if the id is unknown or the action was already rolled back.
    """
    rt = _runtime()
    try:
        rolled_back = rt.sandbox.rollback(action_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return rolled_back.model_dump()


ALL_TOOLS = [
    load_plan,
    query_invoices,
    fx_convert,
    propose_make_good_invoice,
    propose_credit_memo,
    propose_plan_amendment,
    apply_action,
    rollback_action,
]
