"""DLMS general-glo-ciphering envelope and its AES-GCM decryption.

Layout (DLMS Green Book 9.3; identical at TINETZ, Salzburg Netz,
Energienetze Steiermark and in the Smart Meter 2.0 H1 interface)::

    DB                      general-glo-ciphering (DC = general-ded-ciphering)
    08 <8 bytes>            system title
    <BER length>            length of everything that follows
    SC                      security control byte
    <4 bytes>               frame counter
    <ciphertext>
    [<12 bytes>]            GCM tag, only if SC has the authentication bit

The 12-byte GCM nonce is system title + frame counter. The tag is not
verified: the customer interfaces hand out the encryption key (GUEK) and
not always the authentication key, and a wrong key is detected one layer
up because the plaintext does not parse.
"""

from __future__ import annotations

from dataclasses import dataclass

from Cryptodome.Cipher import AES

from .axdr import AxdrError, decode_length

GLO_CIPHERING_TAGS = (0xDB, 0xDC)
_SYSTEM_TITLE_LENGTH = 8
_FRAME_COUNTER_LENGTH = 4
_TAG_LENGTH = 12
_KEY_LENGTH = 16
_SC_AUTHENTICATED = 0x10
_SC_ENCRYPTED = 0x20
_SC_COMPRESSED = 0x80


class CipherError(ValueError):
    """Raised when an envelope is malformed or cannot be decrypted."""


@dataclass(frozen=True)
class GloCipheredApdu:
    """Parsed fields of a general-glo-ciphering APDU."""

    system_title: bytes
    security_control: int
    frame_counter: bytes
    payload: bytes  # ciphertext (or plaintext if not encrypted), tag stripped

    @property
    def encrypted(self) -> bool:
        return bool(self.security_control & _SC_ENCRYPTED)


def envelope_size(data: bytes) -> int | None:
    """Total size of the envelope at the start of ``data``.

    Returns ``None`` while not enough bytes are buffered to tell, and
    raises ``CipherError`` if ``data`` does not start with an envelope.
    """
    if not data:
        return None
    if data[0] not in GLO_CIPHERING_TAGS:
        raise CipherError(f"not a ciphered APDU (starts with {data[0]:#04x})")
    if len(data) < 2:
        return None
    if data[1] != _SYSTEM_TITLE_LENGTH:
        raise CipherError(f"unexpected system title length {data[1]}")
    length_offset = 2 + _SYSTEM_TITLE_LENGTH
    if len(data) <= length_offset:
        return None
    try:
        length, payload_offset = decode_length(data, length_offset)
    except AxdrError:
        if len(data) < length_offset + 5:
            return None  # long-form length not complete yet
        raise CipherError("invalid envelope length") from None
    return payload_offset + length


def parse_envelope(data: bytes) -> GloCipheredApdu:
    """Parse a complete general-glo-ciphering APDU."""
    size = envelope_size(data)
    if size is None or len(data) < size:
        raise CipherError(f"truncated envelope: have {len(data)} bytes, need {size}")
    system_title = data[2 : 2 + _SYSTEM_TITLE_LENGTH]
    _length, offset = decode_length(data, 2 + _SYSTEM_TITLE_LENGTH)
    if size - offset < 1 + _FRAME_COUNTER_LENGTH:
        raise CipherError("envelope too short for security header")
    security_control = data[offset]
    frame_counter = data[offset + 1 : offset + 1 + _FRAME_COUNTER_LENGTH]
    payload = data[offset + 1 + _FRAME_COUNTER_LENGTH : size]
    if security_control & _SC_AUTHENTICATED:
        if len(payload) < _TAG_LENGTH:
            raise CipherError("envelope too short for authentication tag")
        payload = payload[:-_TAG_LENGTH]
    return GloCipheredApdu(
        system_title=system_title,
        security_control=security_control,
        frame_counter=frame_counter,
        payload=payload,
    )


def decrypt_envelope(data: bytes, key: bytes) -> bytes:
    """Return the plaintext APDU (or DSMR telegram) inside ``data``."""
    envelope = parse_envelope(data)
    if envelope.security_control & _SC_COMPRESSED:
        raise CipherError("compressed APDUs are not supported")
    if not envelope.encrypted:
        return envelope.payload
    if len(key) != _KEY_LENGTH:
        raise CipherError(f"key must be {_KEY_LENGTH} bytes, got {len(key)}")
    nonce = envelope.system_title + envelope.frame_counter
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt(envelope.payload)
