"""AES-GCM decryption of the DLMS APDU embedded in an M-Bus frame.

DLMS Security Suite 0 (as used by the Sagemcom T210-D customer interface)
encrypts the APDU with AES-128-GCM. The 12-byte nonce is the
concatenation of the 8-byte system title and the 4-byte invocation
(frame) counter found in the M-Bus user data.

We do not verify the GCM authentication tag – the reference
implementation at greenMikeEU/SmartMeterEVN does not transmit it in the
on-wire layout that the T210-D exposes to the customer interface, and
the parsed DLMS APDU carries its own structural integrity check
(``pduToXml`` rejects malformed input).
"""

from __future__ import annotations

from Cryptodome.Cipher import AES

_KEY_LENGTH = 16
_NONCE_LENGTH = 12


class DecryptionError(ValueError):
    """Raised when AES-GCM decryption cannot proceed."""


def aes_gcm_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    """Decrypt ``ciphertext`` with AES-128-GCM using ``key`` and ``nonce``."""
    if len(key) != _KEY_LENGTH:
        raise DecryptionError(
            f"key must be {_KEY_LENGTH} bytes, got {len(key)}"
        )
    if len(nonce) != _NONCE_LENGTH:
        raise DecryptionError(
            f"nonce must be {_NONCE_LENGTH} bytes, got {len(nonce)}"
        )
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt(ciphertext)
