"""Commit hash detection for client/server version negotiation."""

from __future__ import annotations

import os
import subprocess


def _detect_from_git() -> str:
    """Return the current git HEAD hash, or ``unknown`` if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _load_built_commit() -> str:
    """Return the commit hash embedded at build time, if present."""
    try:
        from smartusbhub_cli._built_commit import COMMIT_HASH  # type: ignore[import]

        return COMMIT_HASH
    except Exception:
        return "unknown"


COMMIT_HASH: str = _detect_from_git() or _load_built_commit() or "unknown"


def get_commit_hash() -> str:
    """Return the commit hash for this build/runtime."""
    return COMMIT_HASH
