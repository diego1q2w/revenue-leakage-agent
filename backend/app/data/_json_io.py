"""Small shared helpers for reading/writing the JSON-array files used as
storage for both the read-only /data inputs and the writable /sandbox
ledgers.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json_list(path: Path) -> list[dict[str, Any]]:
    """Read a JSON array file into a list of dicts.

    Missing or empty files are treated as an empty list rather than an
    error, so tests can point at a fresh tmp_path directory without having
    to pre-seed every ledger file.
    """
    if not path.exists():
        return []
    text = path.read_text()
    if not text.strip():
        return []
    return json.loads(text)


def write_json_list(path: Path, data: list[dict[str, Any]]) -> None:
    """Write a list of dicts back out as a pretty-printed JSON array.

    Writes to a temp file in the same directory and atomically renames it
    into place, so a crash or interruption mid-write can never leave a
    truncated/corrupt ledger file behind for the next read to trip over.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp_file:
            tmp_file.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise
