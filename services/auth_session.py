"""Keep authenticated identity and study state within one browser session."""

from collections.abc import MutableMapping
import time
from typing import Any

from services.auth_service import AuthUser


SESSION_DURATION_SECONDS = 8 * 60 * 60


def start_authenticated_session(
    session_state: MutableMapping[str, Any], user: AuthUser,
) -> None:
    """Start with clean study state whenever an account signs in."""
    session_state.clear()
    session_state["auth_user"] = user
    session_state["auth_started_at"] = time.time()


def logout_session(session_state: MutableMapping[str, Any]) -> None:
    """Forget identity, form credentials, uploads, and all study state."""
    session_state.clear()


def current_user(session_state: MutableMapping[str, Any]) -> AuthUser | None:
    user = session_state.get("auth_user")
    if user is None:
        return None

    started_at = session_state.get("auth_started_at")
    if (
        not isinstance(user, AuthUser)
        or isinstance(started_at, bool)
        or not isinstance(started_at, (int, float))
        or not 0 <= time.time() - started_at < SESSION_DURATION_SECONDS
    ):
        logout_session(session_state)
        return None

    return user
