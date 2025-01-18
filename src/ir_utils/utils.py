"""Utilities."""

from __future__ import annotations

__all__: list[str] = [
    "micros",
]

from datetime import timedelta


def micros(t: timedelta) -> int:
    """Convert a timedelta to microseconds."""
    return t // timedelta(microseconds=1)
