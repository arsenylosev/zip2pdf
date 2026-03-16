from __future__ import annotations

import base64
import hashlib


def _derive_keystream(secret: str, size: int) -> bytes:
    if not secret:
        raise ValueError("LLM_KEYS_ENCRYPTION_KEY is not configured")
    seed = secret.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < size:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        out.extend(digest)
        counter += 1
    return bytes(out[:size])


def encrypt_token(plain: str, secret: str) -> str:
    raw = plain.encode("utf-8")
    key = _derive_keystream(secret, len(raw))
    encrypted = bytes(a ^ b for a, b in zip(raw, key))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_token(ciphertext: str, secret: str) -> str:
    enc = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    key = _derive_keystream(secret, len(enc))
    plain = bytes(a ^ b for a, b in zip(enc, key))
    return plain.decode("utf-8")


def mask_token(token: str) -> str:
    token = token.strip()
    if len(token) <= 10:
        return "*" * len(token)
    return f"{token[:5]}{'*' * (len(token) - 9)}{token[-4:]}"
