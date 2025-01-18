# Source: https://gist.github.com/vills/590c154b377ac50acab079328e4ddaf9

"""Based on incredible works:
* @mildsunrise (https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5)
* @elupus (https://github.com/elupus/irgen)
(thank you!).

Script to convert Broadlink base64 encoded remote codes into a format that can be used in Tuya's IR Blasters (ZS06, ZS08, TS1201, UFO-R11).

**Usage:**
    python3 broadlink_to_tuya.py <broadlink_base64_encoded_string>

**Example**
    python3 broadlink_to_tuya.py JgBmAG40DwwPDA8mEAsPJw8MDwwPDA8nDyYPDA8MDwwPJw8mEAsQCw8MDwwPDA8MDwwPDA8LEAsPDA8MDwwPJw8MDwwPCw8MDwwPDA8MDycPDA8LEAsQCw8nDwwPDA8MDwwPCxALDwANBQAA

Broadlink's IR codes can be found in SmartIR repository (https://github.com/smartHomeHub/SmartIR)
"""

import io
import logging
import sys
from base64 import b64decode, encodebytes
from bisect import bisect
from itertools import islice
from os.path import basename
from struct import pack

from loguru import logger

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def decode_broadlink(data):
    """Generate raw values from broadlink data."""
    v = iter(data)
    code = next(v)
    next(v)  # repeat

    assert code == 0x26  # IR

    length = int.from_bytes(islice(v, 2), byteorder="little")
    assert length >= 3  # a At least trailer

    def decode_iter(x):
        while True:
            try:
                d = next(x)
            except StopIteration:
                return
            if d == 0:
                d = int.from_bytes(islice(x, 2), byteorder="big")

            ms = int(round(d * 8192 / 269, 0))

            # skip last time interval
            if ms > 65535:
                return

            yield ms

    yield from decode_iter(islice(v, length))

    rem = list(v)
    if any(rem):
        log.warning("Ignored extra data: %s", rem)


def decode_broadlink_base64(data):
    """Generate raw data from a base 64 encoded broadlink data."""
    yield from decode_broadlink(b64decode(data))


def encode_tuya_ir(signal: list[int], compression_level=2) -> str:
    """Encodes an IR signal (see `decode_tuya_ir`)
    into an IR code string for a Tuya blaster.
    """
    payload = b"".join(pack("<H", t) for t in signal)
    compress(out := io.BytesIO(), payload, compression_level)
    payload = out.getvalue()
    return encodebytes(payload).decode("ascii").replace("\n", "")


def emit_literal_blocks(out: io.FileIO, data: bytes) -> None:
    for i in range(0, len(data), 32):
        emit_literal_block(out, data[i : i + 32])


def emit_literal_block(out: io.FileIO, data: bytes) -> None:
    length = len(data) - 1
    assert 0 <= length < (1 << 5)
    out.write(bytes([length]))
    out.write(data)


def emit_distance_block(out: io.FileIO, length: int, distance: int) -> None:
    distance -= 1
    assert 0 <= distance < (1 << 13)
    length -= 2
    assert length > 0
    block = bytearray()
    if length >= 7:
        assert length - 7 < (1 << 8)
        block.append(length - 7)
        length = 7
    block.insert(0, length << 5 | distance >> 8)
    block.append(distance & 0xFF)
    out.write(block)


def compress(out: io.FileIO, data: bytes, level=2):
    """Takes a byte string and outputs a compressed "Tuya stream".
    Implemented compression levels:
    0 - copy over (no compression, 3.1% overhead)
    1 - eagerly use first length-distance pair found (linear)
    2 - eagerly use best length-distance pair found
    3 - optimal compression (n^3).
    """
    if level == 0:
        return emit_literal_blocks(out, data)

    W = 2**13  # window size
    L = 255 + 9  # maximum length

    def distance_candidates():
        return range(1, min(pos, W) + 1)

    def find_length_for_distance(start: int) -> int:
        length = 0
        limit = min(L, len(data) - pos)
        while length < limit and data[pos + length] == data[start + length]:
            length += 1
        return length

    def find_length_candidates():
        return ((find_length_for_distance(pos - d), d) for d in distance_candidates())

    def find_length_cheap():
        return next((c for c in find_length_candidates() if c[0] >= 3), None)

    def find_length_max():
        return max(find_length_candidates(), key=lambda c: (c[0], -c[1]), default=None)

    if level >= 2:
        suffixes = []
        next_pos = 0

        def key(n):
            return data[n:]

        def find_idx(n):
            return bisect(suffixes, key(n), key=key)

        def distance_candidates():
            nonlocal next_pos
            while next_pos <= pos:
                if len(suffixes) == W:
                    suffixes.pop(find_idx(next_pos - W))
                suffixes.insert(idx := find_idx(next_pos), next_pos)
                next_pos += 1
            idxs = (idx + i for i in (+1, -1))  # try +1 first
            return (pos - suffixes[i] for i in idxs if 0 <= i < len(suffixes))

    if level <= 2:
        find_length = {1: find_length_cheap, 2: find_length_max}[level]
        block_start = pos = 0
        while pos < len(data):
            if (c := find_length()) and c[0] >= 3:
                emit_literal_blocks(out, data[block_start:pos])
                emit_distance_block(out, c[0], c[1])
                pos += c[0]
                block_start = pos
            else:
                pos += 1
        emit_literal_blocks(out, data[block_start:pos])
        return None

    # use topological sort to find shortest path
    predecessors = [(0, None, None)] + [None] * len(data)

    def put_edge(cost, length, distance) -> None:
        npos = pos + length
        cost += predecessors[pos][0]
        current = predecessors[npos]
        if not current or cost < current[0]:
            predecessors[npos] = cost, length, distance

    for pos in range(len(data)):
        if c := find_length_max():
            for length in range(3, c[0] + 1):
                put_edge(2 if length < 9 else 3, length, c[1])
        for bit_length in range(1, min(32, len(data) - pos) + 1):
            put_edge(1 + bit_length, bit_length, 0)

    # reconstruct path, emit blocks
    blocks = []
    pos = len(data)
    while pos > 0:
        _, length, distance = predecessors[pos]
        pos -= length
        blocks.append((pos, length, distance))
    for pos, length, distance in reversed(blocks):
        if not distance:
            emit_literal_block(out, data[pos : pos + length])
        else:
            emit_distance_block(out, length, distance)
    return None


def main() -> None:
    if len(sys.argv) != 2:
        logger.info(
            f"Usage: python {basename(__file__)} <broadlink_base64_encoded_string>",
        )
        sys.exit(1)

    raw_data = list(decode_broadlink_base64(sys.argv[1]))
    log.info("Raw data: %s", raw_data)

    tuya_data = encode_tuya_ir(raw_data)
    log.info("Tuya code: %s", tuya_data)


if __name__ == "__main__":
    main()
