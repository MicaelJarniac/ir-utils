"""Tests for the `utils` module."""

from __future__ import annotations

from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from ir_utils.utils import micros


@given(microseconds=st.integers(min_value=-999_999_999, max_value=999_999_999))
def test_micros(microseconds: int) -> None:
    """Test the `micros` function."""
    assert micros(timedelta(microseconds=microseconds)) == microseconds
