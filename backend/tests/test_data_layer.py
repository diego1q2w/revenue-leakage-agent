"""Data layer tests.

Repository tests read the real, read-only ./data fixtures. Sandbox and
proposal-store tests always point at a pytest tmp_path directory so they
never touch the real ./sandbox.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.config import get_settings
from backend.app.data.models import ActionDraft
from backend.app.data.proposals import ProposalStore
from backend.app.data.repositories import (
    CreditMemoRepository,
    ExchangeRateRepository,
    InvoiceRepository,
    PlanRepository,
)
from backend.app.data.sandbox import SandboxLedger

DATA_DIR = get_settings().data_dir


# --------------------------------------------------------------------------
# PlanRepository
# --------------------------------------------------------------------------


def test_plan_repository_get_returns_plan_by_id():
    """PlanRepository.get returns the plan matching plan_id."""
    repo = PlanRepository(DATA_DIR)
    plan = repo.get("C-1001")
    assert plan is not None
    assert plan.customer_name == "ACME Corp"
    assert plan.cadence == "Monthly"


def test_plan_repository_get_unknown_id_returns_none():
    repo = PlanRepository(DATA_DIR)
    assert repo.get("does-not-exist") is None


def test_plan_repository_list_all_includes_amendment_plan():
    """The C-1007-A1 amendment plan is listed and carries its `amends` link."""
    repo = PlanRepository(DATA_DIR)
    plans = repo.list_all()
    assert len(plans) == 4
    amendment = next(p for p in plans if p.plan_id == "C-1007-A1")
    assert amendment.amends == "C-1007"
    original = next(p for p in plans if p.plan_id == "C-1007")
    assert original.amends is None


# --------------------------------------------------------------------------
# InvoiceRepository
# --------------------------------------------------------------------------


def test_invoice_repository_query_by_plan():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(plan_id="C-1001")
    assert len(invoices) == 9
    assert all(inv.plan_id == "C-1001" for inv in invoices)


def test_invoice_repository_query_by_customer():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(customer_name="Globex Ltd")
    ids = {inv.invoice_id for inv in invoices}
    assert ids == {"I-9110", "I-9123", "I-9202"}


def test_invoice_repository_query_by_date_range_inclusive():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(date_from="2025-01-01", date_to="2025-01-05")
    assert {inv.invoice_id for inv in invoices} == {"I-9001"}


def test_invoice_repository_query_combines_filters():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(plan_id="C-1001", date_from="2025-03-01", date_to="2025-04-30")
    assert {inv.invoice_id for inv in invoices} == {"I-9003", "I-9004"}


def test_invoice_repository_no_filters_returns_all_including_orphan():
    """query() with no filters returns every invoice, and the orphan invoice
    (empty plan_id) is present and doesn't crash parsing/filtering."""
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query()
    assert len(invoices) == 13
    orphan = next(inv for inv in invoices if inv.invoice_id == "I-9202")
    assert orphan.plan_id == ""


def test_invoice_repository_query_by_empty_plan_id_finds_orphan():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(plan_id="")
    assert {inv.invoice_id for inv in invoices} == {"I-9202"}


# --------------------------------------------------------------------------
# CreditMemoRepository
# --------------------------------------------------------------------------


def test_invoice_repository_query_by_invoice_id():
    repo = InvoiceRepository(DATA_DIR)
    invoices = repo.query(invoice_id="I-9123")
    assert len(invoices) == 1
    assert invoices[0].invoice_id == "I-9123"


def test_query_invoices_attaches_credit_memos_for_invoice():
    from backend.app.agent.tools import query_invoices

    rows = query_invoices.invoke({"invoice_id": "I-9123"})
    assert len(rows) == 1
    assert rows[0]["invoice_id"] == "I-9123"
    assert len(rows[0]["credit_memos"]) == 1
    assert rows[0]["credit_memos"][0]["memo_id"] == "M-300"


def test_query_invoices_includes_empty_credit_memos_list():
    from backend.app.agent.tools import query_invoices

    rows = query_invoices.invoke({"invoice_id": "I-9001"})
    assert len(rows) == 1
    assert rows[0]["credit_memos"] == []


def test_credit_memo_repository_list_for_invoice():
    repo = CreditMemoRepository(DATA_DIR)
    memos = repo.list_for_invoice("I-9123")
    assert len(memos) == 1
    assert memos[0].memo_id == "M-300"


def test_credit_memo_repository_list_for_invoice_with_no_memos():
    repo = CreditMemoRepository(DATA_DIR)
    assert repo.list_for_invoice("I-9001") == []


def test_credit_memo_repository_list_all():
    repo = CreditMemoRepository(DATA_DIR)
    memos = repo.list_all()
    assert len(memos) == 1
    assert memos[0].plan_id == "C-1007-A1"


# --------------------------------------------------------------------------
# ExchangeRateRepository / fx_convert
# --------------------------------------------------------------------------


def test_fx_convert_identity_when_same_currency():
    repo = ExchangeRateRepository(DATA_DIR)
    assert repo.convert(100.0, "USD", "USD", "2025-09-12") == 100.0


def test_fx_convert_exact_date_direct_pair():
    """The real data has exactly one EUR->USD rate dated 2025-09-12."""
    repo = ExchangeRateRepository(DATA_DIR)
    result = repo.convert(100.0, "EUR", "USD", "2025-09-12")
    assert result == pytest.approx(108.0)


def test_fx_convert_inverse_pair():
    """USD->EUR isn't in the table directly; it's derived as 1/rate."""
    repo = ExchangeRateRepository(DATA_DIR)
    result = repo.convert(108.0, "USD", "EUR", "2025-09-12")
    assert result == pytest.approx(100.0)


def test_fx_convert_missing_pair_raises_value_error():
    repo = ExchangeRateRepository(DATA_DIR)
    with pytest.raises(ValueError, match="No exchange rate available"):
        repo.convert(100.0, "GBP", "JPY", "2025-09-12")


def test_fx_convert_most_recent_rate_on_or_before_target_date(tmp_path: Path):
    """When there's no exact-date rate, use the most recent rate on/before
    the target date rather than a later one."""
    _write_exchange_rates(
        tmp_path,
        [
            {"date": "2025-01-01", "from_currency": "EUR", "to_currency": "USD", "rate": 1.05},
            {"date": "2025-06-01", "from_currency": "EUR", "to_currency": "USD", "rate": 1.10},
            {"date": "2025-12-01", "from_currency": "EUR", "to_currency": "USD", "rate": 1.20},
        ],
    )
    repo = ExchangeRateRepository(tmp_path)
    result = repo.convert(100.0, "EUR", "USD", "2025-09-01")
    assert result == pytest.approx(110.0)


def test_fx_convert_falls_back_to_closest_rate_when_none_precede_target(tmp_path: Path):
    """If every known rate postdates the target date, fall back to the
    closest one available rather than raising."""
    _write_exchange_rates(
        tmp_path,
        [
            {"date": "2025-06-01", "from_currency": "EUR", "to_currency": "USD", "rate": 1.10},
            {"date": "2025-08-01", "from_currency": "EUR", "to_currency": "USD", "rate": 1.15},
        ],
    )
    repo = ExchangeRateRepository(tmp_path)
    result = repo.convert(100.0, "EUR", "USD", "2025-01-01")
    assert result == pytest.approx(110.0)  # 2025-06-01 is closer than 2025-08-01


def _write_exchange_rates(data_dir: Path, records: list[dict]) -> None:
    import json

    (data_dir / "exchange_rates.json").write_text(json.dumps(records))


# --------------------------------------------------------------------------
# ProposalStore
# --------------------------------------------------------------------------


def test_proposal_store_create_assigns_id_and_persists(tmp_path: Path):
    store = ProposalStore(tmp_path)
    draft = store.create(
        action_type="make_good_invoice",
        payload={"plan_id": "C-1001", "amount": 8000},
        reason="Missing September invoice",
    )
    assert draft.proposal_id
    assert store.get(draft.proposal_id) == draft


def test_proposal_store_get_unknown_returns_none(tmp_path: Path):
    store = ProposalStore(tmp_path)
    assert store.get("PR-999") is None


def test_proposal_store_persists_across_instances(tmp_path: Path):
    """Drafts must survive a backend restart (i.e. a fresh ProposalStore
    instance pointed at the same sandbox_dir)."""
    first = ProposalStore(tmp_path)
    draft = first.create(action_type="credit_memo", payload={}, reason="overbilled")

    second = ProposalStore(tmp_path)
    assert second.get(draft.proposal_id) == draft
    assert len(second.list()) == 1


def test_proposal_store_assigns_incrementing_ids(tmp_path: Path):
    store = ProposalStore(tmp_path)
    first = store.create(action_type="credit_memo", payload={}, reason="a")
    second = store.create(action_type="credit_memo", payload={}, reason="b")
    assert first.proposal_id != second.proposal_id
    assert len(store.list()) == 2


# --------------------------------------------------------------------------
# SandboxLedger
# --------------------------------------------------------------------------


def _draft(action_type: str, proposal_id: str = "PR-001") -> ActionDraft:
    return ActionDraft(
        proposal_id=proposal_id,
        action_type=action_type,
        payload={"plan_id": "C-1001", "amount": 8000},
        reason="Missing September invoice for C-1001",
    )


def test_sandbox_apply_writes_ledger_entry_and_audit_entry(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    applied = ledger.apply(_draft("make_good_invoice"))

    assert applied.action_id == "INV-MG-001"
    assert applied.rolled_back is False

    state = ledger.state()
    assert len(state["invoices"]) == 1
    assert state["invoices"][0]["action_id"] == "INV-MG-001"
    assert state["credit_memos"] == []
    assert state["plan_amendments"] == []

    audit = ledger.audit_log()
    assert len(audit) == 1
    assert audit[0].event == "applied"
    assert audit[0].action_id == "INV-MG-001"


@pytest.mark.parametrize(
    "action_type,ledger_key,prefix",
    [
        ("make_good_invoice", "invoices", "INV-MG"),
        ("credit_memo", "credit_memos", "CM"),
        ("plan_amendment", "plan_amendments", "AMD"),
    ],
)
def test_sandbox_apply_routes_to_correct_ledger_and_prefix(
    tmp_path: Path, action_type: str, ledger_key: str, prefix: str
):
    ledger = SandboxLedger(tmp_path)
    applied = ledger.apply(_draft(action_type))
    assert applied.action_id == f"{prefix}-001"
    assert len(ledger.state()[ledger_key]) == 1


def test_sandbox_apply_same_proposal_twice_raises(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    ledger.apply(_draft("make_good_invoice", proposal_id="PR-001"))
    with pytest.raises(ValueError, match="already been applied"):
        ledger.apply(_draft("make_good_invoice", proposal_id="PR-001"))


def test_sandbox_rollback_marks_row_and_appends_audit_entry(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    applied = ledger.apply(_draft("credit_memo"))

    rolled_back = ledger.rollback(applied.action_id)
    assert rolled_back.rolled_back is True

    state = ledger.state()
    assert len(state["credit_memos"]) == 1  # row kept, not deleted
    assert state["credit_memos"][0]["rolled_back"] is True

    audit = ledger.audit_log()
    assert [entry.event for entry in audit] == ["applied", "rolled_back"]


def test_sandbox_rollback_unknown_action_raises(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    with pytest.raises(ValueError, match="Unknown action_id"):
        ledger.rollback("INV-MG-999")


def test_sandbox_rollback_already_rolled_back_raises(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    applied = ledger.apply(_draft("plan_amendment"))
    ledger.rollback(applied.action_id)
    with pytest.raises(ValueError, match="already been rolled back"):
        ledger.rollback(applied.action_id)


def test_sandbox_audit_log_is_oldest_first(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    a1 = ledger.apply(_draft("make_good_invoice", proposal_id="PR-001"))
    a2 = ledger.apply(_draft("credit_memo", proposal_id="PR-002"))
    ledger.rollback(a1.action_id)

    audit = ledger.audit_log()
    assert [e.action_id for e in audit] == [a1.action_id, a2.action_id, a1.action_id]
    assert [e.event for e in audit] == ["applied", "applied", "rolled_back"]


def test_sandbox_apply_is_race_free_under_concurrent_calls(tmp_path: Path):
    """Concurrent apply() calls for distinct proposals must not lose an
    update or hand out duplicate action_ids — each does a read-modify-write
    of the same ledger file, so this exercises the mutation lock."""
    ledger = SandboxLedger(tmp_path)
    drafts = [_draft("make_good_invoice", proposal_id=f"PR-{i:03d}") for i in range(20)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        applied = list(pool.map(ledger.apply, drafts))

    action_ids = [a.action_id for a in applied]
    assert len(set(action_ids)) == len(drafts)  # no duplicate ids
    assert len(ledger.state()["invoices"]) == len(drafts)  # no lost updates
    assert len(ledger.audit_log()) == len(drafts)


def test_proposal_store_create_is_race_free_under_concurrent_calls(tmp_path: Path):
    """Concurrent create() calls must not lose a draft or collide on id."""
    store = ProposalStore(tmp_path)

    def _create(i: int) -> str:
        return store.create(action_type="credit_memo", payload={"n": i}, reason="x").proposal_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(_create, range(20)))

    assert len(set(ids)) == 20
    assert len(store.list()) == 20


def test_sandbox_reset_clears_ledgers_audit_and_proposals(tmp_path: Path):
    ledger = SandboxLedger(tmp_path)
    proposals = ProposalStore(tmp_path)

    applied = ledger.apply(_draft("make_good_invoice"))
    ledger.rollback(applied.action_id)
    proposals.create(action_type="credit_memo", payload={}, reason="test")

    ledger.reset()

    state = ledger.state()
    assert state == {"invoices": [], "credit_memos": [], "plan_amendments": []}
    assert ledger.audit_log() == []
    assert proposals.list() == []
