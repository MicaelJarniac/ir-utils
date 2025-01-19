"""Tuya protocol implementation."""

from __future__ import annotations

__all__: list[str] = [
    "Tuya",
]

import base64
import io
from dataclasses import dataclass
from datetime import timedelta
from struct import pack, unpack
from typing import TYPE_CHECKING

from ir_utils.compression import fastlz
from ir_utils.protocols import BaseProtocol
from ir_utils.utils import micros

if TYPE_CHECKING:  # pragma: no cover
    from typing import Literal


@dataclass
class Tuya(BaseProtocol[str]):
    """Tuya protocol class."""

    compression_level: Literal[0, 1, 2, 3] = 2

    def from_raw(self, raw: list[timedelta]) -> str:
        """Convert from raw timings to Tuya IR code."""
        payload = b"".join(pack("<H", micros(t)) for t in raw)
        fastlz.compress(out := io.BytesIO(), payload, self.compression_level)
        payload = out.getvalue()
        return base64.encodebytes(payload).decode("ascii").replace("\n", "")

    def to_raw(self, data: str) -> list[timedelta]:
        """Convert Tuya IR code to raw timings."""
        payload = base64.decodebytes(data.encode("ascii"))
        payload = fastlz.decompress(io.BytesIO(payload))

        signal: list[timedelta] = []
        while payload:
            if len(payload) < 2:  # noqa: PLR2004
                msg = f"garbage in decompressed payload: {payload.hex()}"
                raise ValueError(msg)
            signal.append(timedelta(microseconds=unpack("<H", payload[:2])[0]))
            payload = payload[2:]
        return signal
