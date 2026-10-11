"""Password validation and storage without database or UI dependencies."""

import base64
import binascii
import hashlib
import hmac
import re
import secrets


MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128

_SCRYPT_N = 2**17
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAX_MEMORY = 256 * 1024 * 1024
_SALT_LENGTH = 16
_KEY_LENGTH = 32
_FORMAT_PREFIX = f"scrypt$v1$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}"
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_MAX_ENCODED_LENGTH = 256


def validate_password(password: str) -> None:
    """Require 15–128 characters, preserving spaces and Unicode exactly."""
    if not isinstance(password, str):
        raise ValueError("Password must be text.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must contain {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} characters."
        )
    try:
        password.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Password must contain valid Unicode text.") from error


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAX_MEMORY,
        dklen=_KEY_LENGTH,
    )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str, expected_length: int) -> bytes:
    if not _BASE64_PATTERN.fullmatch(value):
        raise ValueError("Invalid password hash encoding.")
    padding = "=" * (-len(value) % 4)
    decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    if len(decoded) != expected_length or _encode(decoded) != value:
        raise ValueError("Invalid password hash length or encoding.")
    return decoded


def hash_password(password: str) -> str:
    """Create a salted, self-describing scrypt hash for database storage."""
    validate_password(password)
    salt = secrets.token_bytes(_SALT_LENGTH)
    key = _derive_key(password, salt)
    return f"{_FORMAT_PREFIX}${_encode(salt)}${_encode(key)}"


def verify_password(password: str, encoded: str) -> bool:
    """Check a stored v1 hash; malformed or unsupported records fail closed."""
    if not isinstance(encoded, str) or len(encoded) > _MAX_ENCODED_LENGTH:
        return False
    try:
        validate_password(password)
        algorithm, version, parameters, encoded_salt, encoded_key = encoded.split("$")
        # Only known parameters may reach scrypt. Future formats need an explicit
        # verifier instead of accepting arbitrary resource costs from a record.
        if "$".join((algorithm, version, parameters)) != _FORMAT_PREFIX:
            return False
        salt = _decode(encoded_salt, _SALT_LENGTH)
        expected_key = _decode(encoded_key, _KEY_LENGTH)
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(_derive_key(password, salt), expected_key)
