"""Shared lazily-built handles to data-layer collaborators.

Tools, sandbox API routes, and tests all resolve repositories and ledgers
through this module so DATA_DIR / SANDBOX_DIR always agree. Call
`get_runtime.cache_clear()` after changing settings in tests.
"""

from functools import lru_cache
from types import SimpleNamespace

from backend.app.config import get_settings
from backend.app.data.proposals import ProposalStore
from backend.app.data.repositories import (
    CreditMemoRepository,
    ExchangeRateRepository,
    InvoiceRepository,
    PlanRepository,
)
from backend.app.data.sandbox import SandboxLedger


@lru_cache(maxsize=1)
def get_runtime() -> SimpleNamespace:
    settings = get_settings()
    return SimpleNamespace(
        plans=PlanRepository(settings.data_dir),
        invoices=InvoiceRepository(settings.data_dir),
        credit_memos=CreditMemoRepository(settings.data_dir),
        fx=ExchangeRateRepository(settings.data_dir),
        proposals=ProposalStore(settings.sandbox_dir),
        sandbox=SandboxLedger(settings.sandbox_dir),
    )
