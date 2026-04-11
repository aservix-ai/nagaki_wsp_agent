"""Helpers for comparing and selecting qualification snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def _parse_snapshot_version(snapshot: Mapping[str, Any]) -> int:
    try:
        return int(snapshot.get("version", -1))
    except (TypeError, ValueError):
        return -1


def _parse_snapshot_updated_at(snapshot: Mapping[str, Any]) -> float:
    raw = snapshot.get("updated_at")
    if not isinstance(raw, str) or not raw.strip():
        return -1.0

    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return -1.0


def pick_fresher_snapshot(*snapshots: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the freshest snapshot among the provided candidates."""
    candidates = [dict(snapshot) for snapshot in snapshots if isinstance(snapshot, Mapping)]
    if not candidates:
        return {}

    def sort_key(snapshot: Mapping[str, Any]) -> tuple[int, float, int, int]:
        return (
            _parse_snapshot_version(snapshot),
            _parse_snapshot_updated_at(snapshot),
            int(bool(snapshot.get("interested"))),
            int(bool(snapshot.get("qualified"))),
        )

    return max(candidates, key=sort_key)
