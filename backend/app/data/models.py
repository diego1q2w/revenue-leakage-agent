"""Domain models mirroring the JSON files in /data and /sandbox."""

from typing import Any, Literal

from pydantic import BaseModel


class BillingPlan(BaseModel):
    """A contracted billing plan (data/billing_plans.json)."""

    plan_id: str
    customer_name: str
    total_value: float
    currency: str
    cadence: Literal["Monthly", "Quarterly", "Annual"]
    start_date: str
    entitlements: list[str] = []
    notes: str | None = None
    amends: str | None = None
    """plan_id of the plan this record amends, if any (e.g. C-1007-A1 amends C-1007)."""


class Invoice(BaseModel):
    """An issued invoice (data/invoices.json)."""

    invoice_id: str
    plan_id: str
    """May be an empty string for an orphan invoice with no matching plan."""
    customer_name: str
    issue_date: str
    due_date: str
    amount_invoiced: float
    currency: str
    status: Literal["paid", "unpaid"]
    description: str | None = None


class CreditMemo(BaseModel):
    """An existing credit memo (data/credit_memos.json)."""

    memo_id: str
    plan_id: str
    invoice_id: str
    amount: float
    currency: str
    issue_date: str
    reason: str | None = None


class ExchangeRate(BaseModel):
    """A single dated FX rate record (data/exchange_rates.json)."""

    date: str
    from_currency: str
    to_currency: str
    rate: float


class ActionDraft(BaseModel):
    """A proposed corrective action, not yet applied to the sandbox."""

    proposal_id: str
    action_type: Literal["make_good_invoice", "credit_memo", "plan_amendment"]
    payload: dict[str, Any]
    reason: str


class AppliedAction(BaseModel):
    """A corrective action that has been written to the sandbox."""

    action_id: str
    draft: ActionDraft
    applied_at: str
    rolled_back: bool = False
    rolled_back_at: str | None = None


class AuditEntry(BaseModel):
    """One row in sandbox/audit_log.json."""

    action_id: str
    event: Literal["applied", "rolled_back"]
    timestamp: str
    detail: dict[str, Any] = {}
