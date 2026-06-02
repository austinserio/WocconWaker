"""Secure token generation and verification for invites and password reset."""
import hashlib
import secrets


def generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex_hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_token(raw: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_token(raw), stored_hash)
