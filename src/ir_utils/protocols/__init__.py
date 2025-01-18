"""IR protocols."""

from __future__ import annotations

__all__: list[str] = [
    "BaseProtocol",
    "convert",
]

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from datetime import timedelta


@dataclass
class BaseProtocol[T](ABC):
    """Base protocol class."""

    @abstractmethod
    def from_raw(self, raw: list[timedelta]) -> T:
        """Convert from raw timings to protocol object."""

    @abstractmethod
    def to_raw(self, data: T) -> list[timedelta]:
        """Convert protocol object to raw timings."""


def convert[T, U](
    from_protocol: BaseProtocol[T],
    to_protocol: BaseProtocol[U],
    data: T,
) -> U:
    """Convert from one protocol to another.

    Args:
        from_protocol: The protocol to convert from.
        to_protocol: The protocol to convert to.
        data: The data to convert.

    Returns:
        The converted data.
    """
    return to_protocol.from_raw(from_protocol.to_raw(data))
