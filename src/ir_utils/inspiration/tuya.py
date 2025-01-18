"""Convert between Tuya and raw IR data."""
# Source: https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5

from __future__ import annotations

__all__: list[str] = []

import base64
import io
from bisect import bisect
from collections.abc import MutableSequence
from struct import pack, unpack
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Literal


def decode_ir(code: str) -> list[int]:
    """Decodes an IR code string from a Tuya blaster.

    Returns the IR signal as a list of µs durations,
    with the first duration belonging to a high state.
    """
    payload = base64.decodebytes(code.encode("ascii"))
    payload = decompress(io.BytesIO(payload))

    signal = []
    while payload:
        if len(payload) < 2:  # noqa: PLR2004
            msg = f"garbage in decompressed payload: {payload.hex()}"
            raise ValueError(msg)
        signal.append(unpack("<H", payload[:2])[0])
        payload = payload[2:]
    return signal


def encode_ir(signal: list[int], compression_level: Literal[0, 1, 2, 3] = 2) -> str:
    """Encodes an IR signal (see `decode_tuya_ir`) into an IR code string for a Tuya blaster."""  # noqa: E501
    payload = b"".join(pack("<H", t) for t in signal)
    compress(out := io.BytesIO(), payload, compression_level)
    payload = out.getvalue()
    return base64.encodebytes(payload).decode("ascii").replace("\n", "")


# DECOMPRESSION


def decompress(inf: io.BytesIO) -> bytes:
    """Reads a "Tuya stream" from a binary file, and returns the decompressed byte string."""  # noqa: E501
    out = bytearray()

    while header := inf.read(1):
        length, distance = header[0] >> 5, header[0] & 0b11111
        if not length:
            # literal block
            length = distance + 1
            data = inf.read(length)
            if len(data) != length:
                msg = "unexpected end of stream"
                raise ValueError(msg)
        else:
            # length-distance pair block
            if length == 7:  # noqa: PLR2004
                length += inf.read(1)[0]
            length += 2
            distance = (distance << 8 | inf.read(1)[0]) + 1
            data = bytearray()
            while len(data) < length:
                data.extend(out[-distance:][: length - len(data)])
        out.extend(data)

    return bytes(out)


# COMPRESSION


def emit_literal_blocks(out: io.BytesIO, data: bytes) -> None:
    for i in range(0, len(data), 32):
        emit_literal_block(out, data[i : i + 32])


def emit_literal_block(out: io.BytesIO, data: bytes) -> None:
    length = len(data) - 1
    if not (0 <= length < (1 << 5)):
        msg = f"invalid length: {length}"
        raise ValueError(msg)
    out.write(bytes([length]))
    out.write(data)


def emit_distance_block(out: io.BytesIO, length: int, distance: int) -> None:
    distance -= 1
    if not (0 <= distance < (1 << 13)):
        msg = f"invalid distance: {distance}"
        raise ValueError(msg)
    length -= 2
    if length <= 0:
        msg = f"invalid length: {length}"
        raise ValueError
    block = bytearray()
    if length >= 7:  # noqa: PLR2004
        if not (length - 7 < (1 << 8)):
            msg = f"invalid length: {length}"
            raise ValueError(msg)
        block.append(length - 7)
        length = 7
    block.insert(0, length << 5 | distance >> 8)
    block.append(distance & 0xFF)
    out.write(block)


def compress(out: io.BytesIO, data: bytes, level: Literal[0, 1, 2, 3] = 2) -> None:  # noqa: C901, PLR0912, PLR0915
    """Takes a byte string and outputs a compressed "Tuya stream".

    Implemented compression levels:
    0 - copy over (no compression, 3.1% overhead)
    1 - eagerly use first length-distance pair found (linear)
    2 - eagerly use best length-distance pair found
    3 - optimal compression (n^3)
    """
    if level == 0:
        return emit_literal_blocks(out, data)

    window_size = 2**13
    max_len = 255 + 9

    def distance_candidates() -> Iterable[int]:
        return range(1, min(pos, window_size) + 1)

    def find_length_for_distance(start: int) -> int:
        length = 0
        limit = min(max_len, len(data) - pos)
        while length < limit and data[pos + length] == data[start + length]:
            length += 1
        return length

    def find_length_candidates() -> Iterable[tuple[int, int]]:
        return ((find_length_for_distance(pos - d), d) for d in distance_candidates())

    def find_length_cheap() -> tuple[int, int] | None:
        return next((c for c in find_length_candidates() if c[0] >= 3), None)  # noqa: PLR2004

    def find_length_max() -> tuple[int, int] | None:
        def get_key(c: tuple[int, int] | None) -> tuple[int, int]:
            if c is None:
                msg = "no length-distance pair found"
                raise ValueError(msg)
            return c[0], -c[1]

        return max(find_length_candidates(), key=get_key, default=None)

    if level >= 2:  # noqa: PLR2004
        suffixes: list[int] = []
        next_pos = 0

        def key(n: int) -> bytes:
            return data[n:]

        def find_idx(n: int) -> int:
            return bisect(suffixes, key(n), key=key)

        def distance_candidates() -> Iterable[int]:
            nonlocal next_pos
            while next_pos <= pos:
                if len(suffixes) == window_size:
                    suffixes.pop(find_idx(next_pos - window_size))
                suffixes.insert(idx := find_idx(next_pos), next_pos)
                next_pos += 1
            idxs = (idx + i for i in (+1, -1))  # try +1 first
            return (pos - suffixes[i] for i in idxs if 0 <= i < len(suffixes))

    if level <= 2:  # noqa: PLR2004
        find_length = {1: find_length_cheap, 2: find_length_max}[level]
        block_start = pos = 0
        while pos < len(data):
            if (length_max := find_length()) and length_max[0] >= 3:  # noqa: PLR2004
                emit_literal_blocks(out, data[block_start:pos])
                emit_distance_block(out, length_max[0], length_max[1])
                pos += length_max[0]
                block_start = pos
            else:
                pos += 1
        emit_literal_blocks(out, data[block_start:pos])
        return None

    # use topological sort to find shortest path
    predecessors: MutableSequence[tuple[int, int | None, int | None] | None] = [
        (0, None, None),
    ] + [None] * len(data)

    def put_edge(cost: int, length: int, distance: int) -> None:
        next_pos = pos + length
        predecessors_pos = predecessors[pos]
        if predecessors_pos is None:
            msg = f"no predecessor for position {pos}"
            raise ValueError(msg)
        cost += predecessors_pos[0]
        current = predecessors[next_pos]
        if not current or cost < current[0]:
            predecessors[next_pos] = cost, length, distance

    for pos in range(len(data)):
        if length_max := find_length_max():
            for length in range(3, length_max[0] + 1):
                put_edge(2 if length < 9 else 3, length, length_max[1])  # noqa: PLR2004
        for length in range(1, min(32, len(data) - pos) + 1):
            put_edge(1 + length, length, 0)

    predecessors_ready = cast(MutableSequence[tuple[int, int, int]], predecessors)

    # reconstruct path, emit blocks
    blocks: list[tuple[int, int, int]] = []
    pos = len(data)
    while pos > 0:
        _, length, distance = predecessors_ready[pos]
        pos -= length
        blocks.append((pos, length, distance))
    for pos, length, distance in reversed(blocks):
        if not distance:
            emit_literal_block(out, data[pos : pos + length])
        else:
            emit_distance_block(out, length, distance)
    return None
