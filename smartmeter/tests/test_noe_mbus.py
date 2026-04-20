"""Unit tests for Netz NÖ M-Bus long-frame parsing."""

import pytest

from meter.noe.mbus import MBusFrame, MBusFrameError


# Synthetic frame layout (hex offsets, bytes in brackets / chars in the hex string):
#   [0..4]   68 LL LL 68                     M-Bus long frame start (LL = user data length)
#   [4..11]  C-field, A-field, CI, 13 bytes of DLMS header + system title tag + len
#   [11..19] 8-byte system title                                 (hex chars 22..38)
#   [19..22] security control + 4-byte frame counter             (hex chars 44..52)
#   [22..N]  encrypted APDU
#   [N..N+2] checksum + 16                                       (M-Bus trailer)
#
# We build a minimal valid frame for happy-path parsing.

SYSTEM_TITLE = bytes.fromhex("4B464D1020200412")  # 8 bytes
FRAME_COUNTER = bytes.fromhex("00000001")  # 4 bytes
CIPHERTEXT = bytes.fromhex("DEADBEEFCAFEBABE" * 4)  # 32 bytes


def _build_frame(
    system_title: bytes = SYSTEM_TITLE,
    frame_counter: bytes = FRAME_COUNTER,
    ciphertext: bytes = CIPHERTEXT,
    *,
    corrupt_trailer: bool = False,
) -> str:
    """Synthesize a valid M-Bus long frame.

    Offsets (inclusive of the 4-byte ``68 LL LL 68`` header) must place
    the system title at byte 11 and the frame counter at byte 22 so the
    parser's fixed offsets line up.
    """
    pre = bytes(7)  # bytes 4..10: pre-header filler (C/A/CI + DLMS preamble)
    mid = bytes(3)  # bytes 19..21: security byte + 1-byte FC length prefix
    user_data = pre + system_title + mid + frame_counter + ciphertext
    length = len(user_data)
    checksum = sum(user_data) & 0xFF
    trailer_end = 0x00 if corrupt_trailer else 0x16
    frame = bytes([0x68, length, length, 0x68]) + user_data + bytes([checksum, trailer_end])
    return frame.hex()


def test_parse_extracts_system_title_counter_and_ciphertext() -> None:
    frame_hex = _build_frame()
    parsed = MBusFrame.parse(frame_hex)
    assert parsed.system_title == SYSTEM_TITLE
    assert parsed.frame_counter == FRAME_COUNTER
    assert parsed.ciphertext == CIPHERTEXT


def test_parse_rejects_wrong_start_byte() -> None:
    with pytest.raises(MBusFrameError, match="start"):
        MBusFrame.parse("FFFFFFFF" + "00" * 40)


def test_parse_rejects_mismatched_length_bytes() -> None:
    # two length bytes must match (68 LL LL 68)
    with pytest.raises(MBusFrameError, match="length"):
        MBusFrame.parse("6810206800" * 5)


def test_parse_rejects_missing_trailer() -> None:
    with pytest.raises(MBusFrameError, match="trailer"):
        MBusFrame.parse(_build_frame(corrupt_trailer=True))


def test_parse_rejects_short_input() -> None:
    with pytest.raises(MBusFrameError):
        MBusFrame.parse("6804046801020304")
