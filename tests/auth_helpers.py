"""Authenticated app setup for tests that exercise the existing dashboard."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.auth_service import AuthUser
from services.auth_session import start_authenticated_session


TEST_USER = AuthUser(
    user_id="11111111-1111-4111-8111-111111111111",
    username="teststudent",
)


def signed_in_app(path: str | Path) -> AppTest:
    """Create an authenticated app without contacting the account database."""
    app = AppTest.from_file(str(path))
    authenticated_state = {}
    start_authenticated_session(authenticated_state, TEST_USER)
    for key, value in authenticated_state.items():
        app.session_state[key] = value
    return app
