"""Persistent store for action drafts proposed by the agent but not yet
applied to the sandbox (sandbox/proposals.json).

Drafts must survive a backend restart, so every mutation is written straight
through to disk rather than cached in memory.
"""

import threading
from pathlib import Path
from typing import Any, Literal

from backend.app.data._json_io import read_json_list, write_json_list
from backend.app.data.models import ActionDraft

# Serializes proposal creation across all ProposalStore instances, for the
# same reason SandboxLedger locks its mutations: proposal_ids are assigned
# from `len(existing) + 1`, so two interleaved creates could otherwise
# compute the same id and one draft would silently overwrite the other.
_creation_lock = threading.Lock()


class ProposalStore:
    """Create, fetch, and list proposed (not-yet-applied) action drafts."""

    def __init__(self, sandbox_dir: Path) -> None:
        self._path = sandbox_dir / "proposals.json"

    def create(
        self,
        action_type: Literal["make_good_invoice", "credit_memo", "plan_amendment"],
        payload: dict[str, Any],
        reason: str,
    ) -> ActionDraft:
        """Persist a new draft and assign it a readable proposal_id."""
        with _creation_lock:
            drafts = self.list()
            proposal_id = f"PR-{len(drafts) + 1:03d}"
            draft = ActionDraft(
                proposal_id=proposal_id,
                action_type=action_type,
                payload=payload,
                reason=reason,
            )
            write_json_list(self._path, [d.model_dump() for d in [*drafts, draft]])
            return draft

    def get(self, proposal_id: str) -> ActionDraft | None:
        """Return a single draft by id, or None if it doesn't exist."""
        for draft in self.list():
            if draft.proposal_id == proposal_id:
                return draft
        return None

    def list(self) -> list[ActionDraft]:
        """Return every proposed draft, in creation order."""
        return [ActionDraft.model_validate(row) for row in read_json_list(self._path)]
