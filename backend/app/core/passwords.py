from __future__ import annotations

import bcrypt


MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) < 12:
        raise ValueError("Password must contain at least 12 UTF-8 bytes")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError("Password cannot exceed 72 UTF-8 bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False