"""Writable sandbox ledger — where approved corrective actions land.

All writes go to /sandbox/*.json; every apply/rollback is recorded in
sandbox/audit_log.json.
"""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from backend.app.data._json_io import read_json_list, write_json_list
from backend.app.data.models import ActionDraft, AppliedAction, AuditEntry

# Serializes every ledger mutation (apply/rollback/reset) across all
# SandboxLedger instances. FastAPI can run sync request handlers in a
# thread pool, so two requests could otherwise interleave a
# read-modify-write cycle on the same JSON file and silently drop one of
# them, or hand out duplicate action ids. A single process-wide lock is
# the simplest correct fix given this app only ever points at one
# sandbox_dir; it would need to become a per-directory lock (or a real
# file lock) if that assumption ever changes.
_mutation_lock = threading.Lock()

# action_type -> ledger filename and readable-id prefix.
_LEDGER_FILES: dict[str, str] = {
    "make_good_invoice": "invoices.json",
    "credit_memo": "credit_memos.json",
    "plan_amendment": "plan_amendments.json",
}
_ID_PREFIXES: dict[str, str] = {
    "make_good_invoice": "INV-MG",
    "credit_memo": "CM",
    "plan_amendment": "AMD",
}
_AUDIT_FILE = "audit_log.json"
_PROPOSALS_FILE = "proposals.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SandboxLedger:
    """Apply, roll back, and inspect corrective actions in the sandbox."""

    def __init__(self, sandbox_dir: Path) -> None:
        self._dir = sandbox_dir

    def apply(self, draft: ActionDraft) -> AppliedAction:
        """Write an approved action draft to the appropriate ledger file
        and append an `applied` entry to the audit log.

        Raises ValueError if this proposal_id has already been applied
        (checked within its own action_type's ledger — proposal ids are
        assigned by ProposalStore and are unique regardless of type).
        """
        if draft.action_type not in _LEDGER_FILES:
            raise ValueError(f"Unknown action_type: {draft.action_type!r}")

        with _mutation_lock:
            ledger_path = self._dir / _LEDGER_FILES[draft.action_type]
            rows = read_json_list(ledger_path)

            if any(row.get("draft", {}).get("proposal_id") == draft.proposal_id for row in rows):
                raise ValueError(
                    f"Proposal {draft.proposal_id!r} has already been applied to the sandbox."
                )

            action_id = f"{_ID_PREFIXES[draft.action_type]}-{len(rows) + 1:03d}"
            applied = AppliedAction(
                action_id=action_id,
                draft=draft,
                applied_at=_now(),
                rolled_back=False,
            )
            rows.append(applied.model_dump())
            write_json_list(ledger_path, rows)

            self._append_audit(
                event="applied",
                action_id=action_id,
                detail={"action_type": draft.action_type, "proposal_id": draft.proposal_id},
            )
            return applied

    def rollback(self, action_id: str) -> AppliedAction:
        """Undo a previously applied action and append a `rolled_back`
        entry to the audit log.

        The ledger row is kept and flagged rather than deleted, preserving
        history. Raises ValueError for an unknown or already-rolled-back
        action_id.
        """
        with _mutation_lock:
            located = self._find_row(action_id)
            if located is None:
                raise ValueError(f"Unknown action_id: {action_id!r}")

            path, rows, index = located
            row = rows[index]
            if row.get("rolled_back"):
                raise ValueError(f"Action {action_id!r} has already been rolled back.")

            row["rolled_back"] = True
            row["rolled_back_at"] = _now()
            rows[index] = row
            write_json_list(path, rows)

            self._append_audit(event="rolled_back", action_id=action_id, detail={})
            return AppliedAction.model_validate(row)

    def state(self) -> dict[str, list[dict[str, Any]]]:
        """Return the current contents of all sandbox ledgers."""
        return {
            "invoices": read_json_list(self._dir / _LEDGER_FILES["make_good_invoice"]),
            "credit_memos": read_json_list(self._dir / _LEDGER_FILES["credit_memo"]),
            "plan_amendments": read_json_list(self._dir / _LEDGER_FILES["plan_amendment"]),
        }

    def audit_log(self) -> list[AuditEntry]:
        """Return the audit trail, oldest first."""
        rows = read_json_list(self._dir / _AUDIT_FILE)
        return [AuditEntry.model_validate(row) for row in rows]

    def reset(self) -> None:
        """Empty every ledger, the audit log, and pending proposals.

        Proposals are cleared too (not just ledgers/audit log) because
        `SandboxLedger` and `ProposalStore` both hand out sequential,
        restart-from-1 ids (INV-MG-001, CM-001, AMD-001, PR-001, ...). A
        reset is meant to fully rewind the demo to a clean slate; leaving
        stale proposals behind would let their ids collide with ids
        assigned after the reset.
        """
        with _mutation_lock:
            for filename in (*_LEDGER_FILES.values(), _AUDIT_FILE, _PROPOSALS_FILE):
                write_json_list(self._dir / filename, [])

    def _find_row(self, action_id: str) -> tuple[Path, list[dict[str, Any]], int] | None:
        """Locate the ledger row for `action_id` across all ledger files."""
        for filename in _LEDGER_FILES.values():
            path = self._dir / filename
            rows = read_json_list(path)
            for index, row in enumerate(rows):
                if row.get("action_id") == action_id:
                    return path, rows, index
        return None

    def _append_audit(
        self, event: Literal["applied", "rolled_back"], action_id: str, detail: dict[str, Any]
    ) -> None:
        path = self._dir / _AUDIT_FILE
        entries = read_json_list(path)
        entry = AuditEntry(action_id=action_id, event=event, timestamp=_now(), detail=detail)
        entries.append(entry.model_dump())
        write_json_list(path, entries)
