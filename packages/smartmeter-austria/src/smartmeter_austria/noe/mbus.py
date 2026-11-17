"""M-Bus long-frame parser for the Sagemcom T210-D on Netz NÖ / EVN.

A long frame has the layout::

    68 LL LL 68 | <user_data LL bytes> | CS 16

Inside the user data, at fixed byte offsets (matching the layout produced
by the T210-D customer interface), the frame carries a DLMS system title
and invocation counter followed by the AES-GCM-encrypted APDU:

    byte 11..18  : 8-byte system title
    byte 22..25  : 4-byte frame / invocation counter
    byte 26..    : ciphertext, up to the end of user_data (4+LL)

These offsets mirror the greenMikeEU/SmartMeterEVN reference parser
(with the trailing-byte bug fixed).
"""

from __future__ import annotations

from dataclasses import dataclass

_START_BYTE = 0x68
_STOP_BYTE = 0x16
_SYSTEM_TITLE_OFFSET = 11
_SYSTEM_TITLE_LEN = 8
_FRAME_COUNTER_OFFSET = 22
_FRAME_COUNTER_LEN = 4
_CIPHERTEXT_OFFSET = 26


class MBusFrameError(ValueError):
    """Raised when an M-Bus long frame cannot be parsed."""


@dataclass(frozen=True)
class MBusFrame:
    """A parsed M-Bus long frame containing a DLMS security envelope."""

    system_title: bytes
    frame_counter: bytes
    ciphertext: bytes

    @classmethod
    def parse(cls, frame_hex: str) -> MBusFrame:
        """Parse a hex-encoded M-Bus long frame.

        Raises ``MBusFrameError`` if the frame is malformed.
        """
        try:
            data = bytes.fromhex(frame_hex)
        except ValueError as exc:
            raise MBusFrameError(f"invalid hex data: {exc}") from exc

        if len(data) < 6:
            raise MBusFrameError(
                f"frame too short: {len(data)} bytes, need at least 6"
            )
        if data[0] != _START_BYTE or data[3] != _START_BYTE:
            raise MBusFrameError(
                f"unexpected start bytes: {data[0]:#04x}, {data[3]:#04x}"
            )
        if data[1] != data[2]:
            raise MBusFrameError(
                f"length bytes differ: {data[1]:#04x} vs {data[2]:#04x}"
            )

        length = data[1]
        user_data_end = 4 + length
        trailer_end = user_data_end + 2
        if len(data) < trailer_end:
            raise MBusFrameError(
                f"frame truncated: have {len(data)} bytes, need {trailer_end}"
            )
        if data[trailer_end - 1] != _STOP_BYTE:
            raise MBusFrameError(
                f"missing trailer byte 0x16, got {data[trailer_end - 1]:#04x}"
            )
        if user_data_end < _CIPHERTEXT_OFFSET:
            raise MBusFrameError(
                f"user data too short for DLMS envelope: {length} bytes"
            )

        st_start = _SYSTEM_TITLE_OFFSET
        st_end = st_start + _SYSTEM_TITLE_LEN
        fc_start = _FRAME_COUNTER_OFFSET
        fc_end = fc_start + _FRAME_COUNTER_LEN

        return cls(
            system_title=data[st_start:st_end],
            frame_counter=data[fc_start:fc_end],
            ciphertext=data[_CIPHERTEXT_OFFSET:user_data_end],
        )
