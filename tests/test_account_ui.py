"""Account identity and avatar controls with isolated, synthetic Auth sessions."""

from io import BytesIO
from pathlib import Path
import time

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from services import account_ui
from services.account_profile import AVATAR_STATE_KEY, get_account_avatar, save_account_avatar
from services.auth_service import AuthUser
from services.auth_session import start_authenticated_session
from tests.auth_helpers import TEST_USER, signed_in_app


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
OTHER_USER = AuthUser("22222222-2222-4222-8222-222222222222", "anotherstudent")


def _account_page_script():
    import streamlit as st
    from services.account_ui import render_account_page

    st.set_page_config(layout="wide")
    render_account_page()


def _account_app(user=TEST_USER):
    app = AppTest.from_function(_account_page_script)
    authenticated_state = {}
    start_authenticated_session(authenticated_state, user)
    for key, value in authenticated_state.items():
        app.session_state[key] = value
    return app


def _image_bytes():
    output = BytesIO()
    Image.new("RGB", (24, 32), (54, 88, 150)).save(output, format="PNG")
    return output.getvalue()


def _add_avatar(app):
    state = {}
    start_authenticated_session(state, TEST_USER)
    result = save_account_avatar(state, _image_bytes(), expected_user_id=TEST_USER.user_id)
    assert result.success
    app.session_state[AVATAR_STATE_KEY] = state[AVATAR_STATE_KEY]


@pytest.mark.parametrize("auth_state", ["missing", "expired", "untrusted"])
def test_account_page_requires_a_current_trusted_login(auth_state):
    app = _account_app()
    _add_avatar(app)
    if auth_state == "missing":
        del app.session_state["auth_user"]
    elif auth_state == "expired":
        app.session_state["auth_started_at"] = time.time() - 9 * 60 * 60
    else:
        app.session_state["auth_user"] = {"username": TEST_USER.username}

    app.run()

    assert not app.exception
    assert [message.value for message in app.info] == ["Log in to view your account."]
    assert not app.get("file_uploader")
    assert not app.button
    assert not app.subheader


def test_account_page_displays_canonical_read_only_identity():
    app = _account_app().run()

    assert not app.exception
    assert [heading.value for heading in app.title] == ["My account"]
    assert TEST_USER.username in [heading.value for heading in app.subheader]
    assert TEST_USER.user_id in [text.value for text in app.text]
    assert not app.text_input
    assert len(app.get("file_uploader")) == 1
    assert app.button(key="account_remove_avatar").disabled
    assert "clears when you log out" in " ".join(caption.value for caption in app.caption)


def test_dashboard_sidebar_identifies_the_signed_in_account_and_links_to_account():
    app = signed_in_app(APP_PATH).run()

    assert not app.exception
    sidebar_text = " ".join(item.value for item in app.sidebar.markdown)
    assert TEST_USER.username in sidebar_text
    assert "SIGNED IN AS" in sidebar_text
    assert any(link.proto.label == "My account" for link in app.sidebar.get("page_link"))
    assert app.sidebar.button(key="logout_button").label == "Log out"


@pytest.mark.parametrize("logout_location", ["sidebar", "account_page"])
def test_account_logout_clears_avatar_identity_and_private_study_state(logout_location):
    app = signed_in_app(APP_PATH) if logout_location == "sidebar" else _account_app()
    _add_avatar(app)
    app.session_state["private_account_test_state"] = "private answer"
    app.run()

    key = "logout_button" if logout_location == "sidebar" else "account_logout_button"
    app.button(key=key).click().run()

    assert not app.exception
    assert "auth_user" not in app.session_state
    assert "auth_started_at" not in app.session_state
    assert AVATAR_STATE_KEY not in app.session_state
    assert "private_account_test_state" not in app.session_state
    assert not any(button.label == "Remove photo" for button in app.button)


def test_avatar_remove_returns_to_default_and_stays_removed_after_rerun():
    app = _account_app()
    _add_avatar(app)
    app.run()
    assert not app.button(key="account_remove_avatar").disabled

    app.button(key="account_remove_avatar").click().run()
    app.run()

    assert not app.exception
    assert AVATAR_STATE_KEY not in app.session_state
    assert app.session_state["auth_user"] == TEST_USER
    assert app.button(key="account_remove_avatar").disabled
    assert any("Default avatar" in item.value for item in app.markdown)


def test_switching_identity_cannot_display_the_previous_accounts_avatar():
    app = _account_app()
    _add_avatar(app)
    app.run()
    app.session_state["auth_user"] = OTHER_USER

    app.run()

    assert not app.exception
    assert OTHER_USER.username in [heading.value for heading in app.subheader]
    assert TEST_USER.username not in [heading.value for heading in app.subheader]
    assert AVATAR_STATE_KEY not in app.session_state
    assert app.button(key="account_remove_avatar").disabled


def test_upload_callback_reports_success_for_the_current_account(monkeypatch):
    state = {}
    start_authenticated_session(state, TEST_USER)
    state["isolated_upload"] = BytesIO(_image_bytes())
    monkeypatch.setattr(account_ui.st, "session_state", state)

    account_ui._upload_avatar("isolated_upload", TEST_USER.user_id)

    assert get_account_avatar(state) is not None
    assert state["account_avatar_notice"].success


@pytest.mark.parametrize("change", ["different_account", "expired_session"])
def test_stale_upload_cannot_write_an_avatar_or_notice_after_account_change(monkeypatch, change):
    state = {}
    start_authenticated_session(state, OTHER_USER)
    if change == "expired_session":
        state["auth_started_at"] = time.time() - 9 * 60 * 60
    state["isolated_upload"] = BytesIO(_image_bytes())
    monkeypatch.setattr(account_ui.st, "session_state", state)

    account_ui._upload_avatar("isolated_upload", TEST_USER.user_id)

    assert AVATAR_STATE_KEY not in state
    assert "account_avatar_notice" not in state
    if change == "different_account":
        assert state["auth_user"] == OTHER_USER
    else:
        assert "auth_user" not in state
