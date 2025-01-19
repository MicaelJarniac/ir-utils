"""Tests for the `compression.fastlz` module."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from ir_utils.compression import fastlz

if TYPE_CHECKING:
    from typing import Literal


@pytest.mark.parametrize("level", [0, 1, 2, 3])
@given(data=st.binary(min_size=10))
def test_compress_decompress(data: bytes, level: Literal[0, 1, 2, 3]) -> None:
    """Test the `compress` and `decompress` functions."""
    assume(any(data))
    compressed = io.BytesIO()
    fastlz.compress(out=compressed, data=data, level=level)
    assert fastlz.decompress(compressed) == data
