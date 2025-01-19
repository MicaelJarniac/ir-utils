"""Tests for the `protocols.tuya` module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from ir_utils.protocols import convert
from ir_utils.protocols.tuya import Tuya

from . import st_raw_ir

if TYPE_CHECKING:  # pragma: no cover
    from datetime import timedelta
    from typing import Literal


@pytest.mark.parametrize("compression", [0, 1, 2, 3])
@given(raw=st_raw_ir())
def test_tuya(raw: list[timedelta], compression: Literal[0, 1, 2, 3]) -> None:
    """Test Tuya."""
    tuya = Tuya(compression_level=compression)
    assert tuya.to_raw(tuya.from_raw(raw)) == raw
    data = tuya.from_raw(raw)
    assert convert(tuya, tuya, data) == data
