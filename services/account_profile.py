"""Validate account avatars without persisting uploads or image metadata.

Avatars belong to one authenticated browser session. Signing out, expiring the
session, or signing into another account removes them; no database is involved.
"""

from collections.abc import MutableMapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any
import warnings

from PIL import Image, ImageOps

from services.auth_service import AuthUser
from services.auth_session import current_user


AVATAR_STATE_KEY = "account_avatar"
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 4_000_000
AVATAR_SIZE = (256, 256)


@dataclass(frozen=True)
class AvatarResult:
    success: bool
    message: str
    error_code: str | None = None


def _avatar_owner(session_state: MutableMapping[str, Any]) -> AuthUser | None:
    user = current_user(session_state)
    stored = session_state.get(AVATAR_STATE_KEY)
    if user is None or (
        stored is not None
        and (not isinstance(stored, dict) or stored.get("user_id") != user.user_id)
    ):
        session_state.pop(AVATAR_STATE_KEY, None)
    return user


def get_account_avatar(session_state: MutableMapping[str, Any]) -> bytes | None:
    """Read the current account's avatar, discarding another account's image."""
    if _avatar_owner(session_state) is None:
        return None
    stored = session_state.get(AVATAR_STATE_KEY)
    if stored is None:
        return None
    image_bytes = stored.get("image_bytes")
    if not isinstance(image_bytes, bytes):
        session_state.pop(AVATAR_STATE_KEY, None)
        return None
    return image_bytes


def _check_owner(
    session_state: MutableMapping[str, Any], expected_user_id: str,
) -> tuple[AuthUser | None, AvatarResult | None]:
    user = _avatar_owner(session_state)
    if user is None:
        return None, AvatarResult(False, "Please sign in to manage your avatar.", "not_authenticated")
    if user.user_id != expected_user_id:
        return None, AvatarResult(
            False, "Your account changed. Please reopen your account page.", "account_changed",
        )
    return user, None


def _normalize_avatar(image_bytes: bytes) -> bytes:
    # Check dimensions before decoding, and avoid changing Pillow's global limits.
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("unsupported_format")
            width, height = image.size
            if width * height > MAX_AVATAR_PIXELS:
                raise ValueError("too_many_pixels")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated_image")
            image.verify()

        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            thumbnail = ImageOps.exif_transpose(image).convert("RGBA")
            thumbnail.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)
            # A fresh canvas omits EXIF, filenames, text chunks, and other metadata.
            normalized = Image.new("RGBA", thumbnail.size)
            normalized.paste(thumbnail)
            output = BytesIO()
            normalized.save(output, format="PNG")
            return output.getvalue()


def save_account_avatar(
    session_state: MutableMapping[str, Any], image_bytes: bytes, *, expected_user_id: str,
) -> AvatarResult:
    """Save a bounded PNG/JPEG thumbnail for the currently authenticated account.

    The expected identity protects against upload callbacks from an earlier
    account. A rejected image leaves the current account's previous avatar intact.
    """
    user, error = _check_owner(session_state, expected_user_id)
    if error is not None:
        return error
    if not isinstance(image_bytes, bytes) or not image_bytes:
        return AvatarResult(False, "Please choose a valid PNG or JPG image.", "invalid_image")
    if len(image_bytes) > MAX_AVATAR_BYTES:
        return AvatarResult(False, "Please choose an image no larger than 2 MB.", "image_too_large")
    try:
        normalized = _normalize_avatar(image_bytes)
    except (
        OSError, ValueError, SyntaxError, OverflowError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ):
        return AvatarResult(
            False,
            "Please choose a valid PNG or JPG image with no more than 4 million pixels.",
            "invalid_image",
        )
    # Decoding happens before storing anything. Recheck identity in case the
    # session expired or an account switch occurred while the image was decoded.
    user, error = _check_owner(session_state, expected_user_id)
    if error is not None:
        return error
    session_state[AVATAR_STATE_KEY] = {"user_id": user.user_id, "image_bytes": normalized}
    return AvatarResult(True, "Avatar updated for this browser session.")


def remove_account_avatar(
    session_state: MutableMapping[str, Any], *, expected_user_id: str,
) -> AvatarResult:
    """Remove only the authenticated account's session avatar."""
    _, error = _check_owner(session_state, expected_user_id)
    if error is not None:
        return error
    session_state.pop(AVATAR_STATE_KEY, None)
    return AvatarResult(True, "Avatar removed.")
