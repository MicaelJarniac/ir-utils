"""Tests for the `protocols` package."""

from __future__ import annotations

__all__: list[str] = []

from datetime import timedelta

from hypothesis import strategies as st


@st.composite
def st_raw_ir(draw: st.DrawFn) -> list[timedelta]:
    """Return a strategy for raw IR data."""
    return draw(
        st.lists(
            st.timedeltas(
                min_value=timedelta(microseconds=0),
                max_value=timedelta(microseconds=65535),
            ),
            max_size=100,
        ),
    )
