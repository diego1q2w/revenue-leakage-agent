"""Read-only repositories over the JSON files in /data."""

from datetime import date
from pathlib import Path

from backend.app.data._json_io import read_json_list
from backend.app.data.models import BillingPlan, CreditMemo, ExchangeRate, Invoice


class PlanRepository:
    """Access to billing plans (data/billing_plans.json)."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "billing_plans.json"

    def get(self, plan_id: str) -> BillingPlan | None:
        """Return a single plan by id, or None if it doesn't exist."""
        for plan in self.list_all():
            if plan.plan_id == plan_id:
                return plan
        return None

    def list_all(self) -> list[BillingPlan]:
        """Return every billing plan."""
        return [BillingPlan.model_validate(row) for row in read_json_list(self._path)]


class InvoiceRepository:
    """Access to issued invoices (data/invoices.json)."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "invoices.json"

    def list_all(self) -> list[Invoice]:
        """Return every invoice, including orphans with an empty plan_id."""
        return [Invoice.model_validate(row) for row in read_json_list(self._path)]

    def query(
        self,
        plan_id: str | None = None,
        customer_name: str | None = None,
        invoice_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Invoice]:
        """Filter invoices by plan, customer, invoice id, and/or issue-date range.

        All filters are optional and combinable. Date bounds are inclusive
        and compare against `issue_date` as zero-padded ISO-8601 strings
        (`YYYY-MM-DD`), which sort lexicographically in chronological
        order — no date parsing is needed as long as the fixtures stay in
        that format.
        """
        invoices = self.list_all()
        if plan_id is not None:
            invoices = [inv for inv in invoices if inv.plan_id == plan_id]
        if customer_name is not None:
            invoices = [inv for inv in invoices if inv.customer_name == customer_name]
        if invoice_id is not None:
            invoices = [inv for inv in invoices if inv.invoice_id == invoice_id]
        if date_from is not None:
            invoices = [inv for inv in invoices if inv.issue_date >= date_from]
        if date_to is not None:
            invoices = [inv for inv in invoices if inv.issue_date <= date_to]
        return invoices


class CreditMemoRepository:
    """Access to existing credit memos (data/credit_memos.json)."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "credit_memos.json"

    def list_for_invoice(self, invoice_id: str) -> list[CreditMemo]:
        """Return credit memos issued against a given invoice."""
        return [memo for memo in self.list_all() if memo.invoice_id == invoice_id]

    def list_all(self) -> list[CreditMemo]:
        """Return every credit memo."""
        return [CreditMemo.model_validate(row) for row in read_json_list(self._path)]


class ExchangeRateRepository:
    """Access to FX rates (data/exchange_rates.json)."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "exchange_rates.json"

    def load(self) -> list[ExchangeRate]:
        """Load every dated FX rate record."""
        return [ExchangeRate.model_validate(row) for row in read_json_list(self._path)]

    def convert(
        self, amount: float, from_ccy: str, to_ccy: str, on_date: str | None = None
    ) -> float:
        """Convert an amount between currencies using the loaded rates.

        Resolution order:
        1. Identity if `from_ccy == to_ccy`.
        2. An exact-date rate for the pair (direct or inverse), if present.
        3. The most recent rate on or before `on_date` (direct or inverse).
        4. The closest available rate for the pair by date (direct or
           inverse), when nothing qualifies on or before `on_date`.

        Direct-currency records are always considered before inverse ones
        when both exist for the very same date, since a same-day direct
        quote is more authoritative than one algebraically derived from
        its inverse; the fixture data never actually has both.

        Raises ValueError if no rate exists for the pair in either
        direction.
        """
        if from_ccy == to_ccy:
            return amount

        records = self.load()
        # (date, effective_rate) — inverse records contribute 1/rate.
        candidates: list[tuple[str, float]] = [
            (r.date, r.rate) for r in records if r.from_currency == from_ccy and r.to_currency == to_ccy
        ] + [
            (r.date, 1.0 / r.rate)
            for r in records
            if r.from_currency == to_ccy and r.to_currency == from_ccy
        ]

        if not candidates:
            raise ValueError(f"No exchange rate available for {from_ccy}->{to_ccy}")

        if on_date is not None:
            exact = [rate for d, rate in candidates if d == on_date]
            if exact:
                return amount * exact[0]

            on_or_before = [(d, rate) for d, rate in candidates if d <= on_date]
            if on_or_before:
                _, rate = max(on_or_before, key=lambda pair: pair[0])
                return amount * rate

            target = date.fromisoformat(on_date)
            _, rate = min(
                candidates, key=lambda pair: abs((date.fromisoformat(pair[0]) - target).days)
            )
            return amount * rate

        # No target date given: fall back to the most recent known rate.
        _, rate = max(candidates, key=lambda pair: pair[0])
        return amount * rate
