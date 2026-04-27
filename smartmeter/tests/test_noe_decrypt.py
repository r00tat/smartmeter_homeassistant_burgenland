"""Unit tests for Netz NÖ AES-GCM decryption."""

import pytest
from Cryptodome.Cipher import AES

from meter.noe.decrypt import DecryptionError, aes_gcm_decrypt


KEY = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
SYSTEM_TITLE = bytes.fromhex("4B464D1020200412")
FRAME_COUNTER = bytes.fromhex("00000001")


def _encrypt(plaintext: bytes) -> bytes:
    cipher = AES.new(KEY, AES.MODE_GCM, nonce=SYSTEM_TITLE + FRAME_COUNTER)
    return cipher.encrypt(plaintext)


def test_roundtrip_decrypt_returns_plaintext() -> None:
    plaintext = b"hello smart meter"
    ciphertext = _encrypt(plaintext)
    got = aes_gcm_decrypt(ciphertext, KEY, SYSTEM_TITLE + FRAME_COUNTER)
    assert got == plaintext


def test_wrong_key_returns_garbage_but_does_not_crash() -> None:
    # GCM without auth-tag verification simply returns garbage for a
    # wrong key; we want the same behaviour the reference uses so that
    # the consumer can test the first few bytes of the APDU.
    plaintext = b"\x0f\x80some dlms payload"
    ciphertext = _encrypt(plaintext)
    wrong_key = b"\x00" * 16
    got = aes_gcm_decrypt(ciphertext, wrong_key, SYSTEM_TITLE + FRAME_COUNTER)
    assert got != plaintext
    assert len(got) == len(plaintext)


def test_short_nonce_rejected() -> None:
    with pytest.raises(DecryptionError, match="nonce"):
        aes_gcm_decrypt(b"abc", KEY, b"\x00" * 4)


def test_short_key_rejected() -> None:
    with pytest.raises(DecryptionError, match="key"):
        aes_gcm_decrypt(b"abc", b"\x00" * 3, SYSTEM_TITLE + FRAME_COUNTER)
