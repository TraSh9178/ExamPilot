"""Account forms and the app gate, with the database calls replaced by spies."""

from pathlib import Path
import time
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from services import auth_ui
from services.i18n import LANGUAGE_KEY, LANGUAGE_WIDGET_KEY
from services.auth_service import AuthResult, AuthUser
from tests.auth_helpers import TEST_USER, signed_in_app


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
PASSWORD = "a private test password"


def submit_login(app: AppTest, username: str, password: str = PASSWORD) -> None:
    app.text_input(key="login_username").set_value(username)
    app.text_input(key="login_password").set_value(password)
    next(button for button in app.button if button.label == "Log in").click().run()


def submit_registration(
    app: AppTest,
    username: str,
    *,
    password: str = PASSWORD,
    confirmation: str = PASSWORD,
) -> None:
    app.text_input(key="register_username").set_value(username)
    app.text_input(key="register_password").set_value(password)
    app.text_input(key="register_password_confirm").set_value(confirmation)
    next(
        button for button in app.button if button.label == "Create account"
    ).click().run()


def assert_auth_gate(app: AppTest) -> None:
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Log in", "Create account"]
    assert "auth_user" not in app.session_state
    assert "courses" not in app.session_state
    assert not any(button.label == "Open course" for button in app.button)
    assert not any(button.label == "Log out" for button in app.button)


def test_logged_out_app_shows_account_forms_before_dashboard(monkeypatch) -> None:
    login = Mock()
    register = Mock()
    monkeypatch.setattr(auth_ui, "login_user", login)
    monkeypatch.setattr(auth_ui, "register_user", register)

    app = AppTest.from_file(str(APP_PATH)).run()

    assert_auth_gate(app)
    assert app.text_input(key="login_password").value == ""
    assert app.text_input(key="register_password").value == ""
    login.assert_not_called()
    register.assert_not_called()


def test_sign_in_page_shows_headline_campus_watercolour_then_account_card(monkeypatch) -> None:
    import base64

    import streamlit as st

    logos = []
    monkeypatch.setattr(st, "logo", lambda *args, **kwargs: logos.append((args, kwargs)))
    app = AppTest.from_file(str(APP_PATH)).run()

    assert_auth_gate(app)
    assert [title.value for title in app.title] == ["Make your next study session count."]
    campus = (APP_PATH.parent / "assets" / "illustrations" / "campus-watercolor.png").read_bytes()
    art = next(item.value for item in app.markdown if 'class="auth-campus"' in item.value)
    assert f'src="data:image/png;base64,{base64.b64encode(campus).decode("ascii")}"' in art
    assert 'alt="Illustration of a university campus"' in art
    assert not any("campus-illustration" in item.value for item in app.markdown)
    # Headline and picture come first, then the Log in / Create account card.
    main = list(app.main)
    title_at = next(i for i, node in enumerate(main) if node.type == "title")
    art_at = next(
        i for i, node in enumerate(main)
        if node.type == "markdown" and 'class="auth-campus"' in node.value
    )
    card_at = next(
        i for i, node in enumerate(main)
        if str(getattr(node.proto, "id", "")).endswith("-auth_forms")
    )
    assert title_at < art_at < card_at
    # The sign-in page has no navigation, so it has no sidebar either.
    assert not app.sidebar.children
    assert [Path(args[0]).name for args, _ in logos] == ["brand-logo.svg"]
    assert "icon_image" not in logos[0][1]


def test_login_language_switch_translates_interface_without_database_calls(monkeypatch) -> None:
    login = Mock()
    register = Mock()
    monkeypatch.setattr(auth_ui, "login_user", login)
    monkeypatch.setattr(auth_ui, "register_user", register)
    app = AppTest.from_file(str(APP_PATH)).run()
    next(item for item in app.get("toggle") if item.key == LANGUAGE_WIDGET_KEY).set_value(True).run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["登录", "创建账户"]
    assert app.text_input(key="login_username").label == "用户名"
    assert app.text_input(key="login_password").label == "密码"
    assert any(button.label == "登录" for button in app.button)
    login.assert_not_called()
    register.assert_not_called()


def test_chinese_choice_continues_to_dashboard_after_login(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_ui, "login_user",
        Mock(return_value=AuthResult(success=True, user=TEST_USER, message="Signed in.")),
    )
    app = AppTest.from_file(str(APP_PATH)).run()
    next(item for item in app.get("toggle") if item.key == LANGUAGE_WIDGET_KEY).set_value(True).run()
    app.text_input(key="login_username").set_value(TEST_USER.username)
    app.text_input(key="login_password").set_value(PASSWORD)
    next(button for button in app.button if button.label == "登录").click().run()

    assert not app.exception
    assert app.session_state[LANGUAGE_KEY] is True
    assert any(button.label == "打开课程" for button in app.button)
    assert app.button(key="logout_button").label == "退出登录"


@pytest.mark.parametrize("method", ["login", "register"])
def test_successful_account_form_opens_dashboard_and_clears_credentials(
    monkeypatch, method: str
) -> None:
    service = Mock(
        return_value=AuthResult(success=True, user=TEST_USER, message="Signed in.")
    )
    monkeypatch.setattr(auth_ui, f"{method}_user", service)
    app = AppTest.from_file(str(APP_PATH)).run()

    if method == "login":
        # Credentials entered in either tab must disappear after authentication.
        app.text_input(key="register_password").set_value("other private password")
        submit_login(app, TEST_USER.username)
    else:
        app.text_input(key="login_password").set_value("other private password")
        submit_registration(app, TEST_USER.username)

    assert not app.exception
    service.assert_called_once_with(TEST_USER.username, PASSWORD)
    assert app.session_state["auth_user"] == TEST_USER
    assert len(app.session_state["courses"]) == 3
    assert any(button.label == "Open course" for button in app.button)
    assert app.button(key="logout_button").label == "Log out"
    for key in (
        "login_username",
        "login_password",
        "register_username",
        "register_password",
        "register_password_confirm",
    ):
        assert key not in app.session_state

    app.run()
    assert not app.exception
    service.assert_called_once()


@pytest.mark.parametrize(
    ("method", "message", "error_code"),
    [
        ("login", "Invalid username or password.", "INVALID_CREDENTIALS"),
        ("register", "That username is already taken.", "USERNAME_TAKEN"),
    ],
)
def test_account_service_failure_stays_on_auth_page(
    monkeypatch, method: str, message: str, error_code: str
) -> None:
    service = Mock(
        return_value=AuthResult(
            success=False, user=None, message=message, error_code=error_code
        )
    )
    monkeypatch.setattr(auth_ui, f"{method}_user", service)
    app = AppTest.from_file(str(APP_PATH)).run()

    if method == "login":
        submit_login(app, TEST_USER.username)
    else:
        submit_registration(app, TEST_USER.username)

    assert_auth_gate(app)
    service.assert_called_once_with(TEST_USER.username, PASSWORD)
    assert message in [error.value for error in app.error]


def test_registration_password_confirmation_stops_before_database(monkeypatch) -> None:
    register = Mock()
    monkeypatch.setattr(auth_ui, "register_user", register)
    app = AppTest.from_file(str(APP_PATH)).run()

    submit_registration(app, TEST_USER.username, confirmation="different password")

    assert_auth_gate(app)
    register.assert_not_called()
    assert app.error


def test_logout_removes_private_state_and_next_account_starts_fresh(monkeypatch) -> None:
    app = signed_in_app(APP_PATH).run()
    private_course = app.session_state["courses"][0].model_copy(
        update={"course_id": "private-course", "course_name": "Private course"}
    )
    private_state = {
        "courses": [private_course],
        "current_course": private_course,
        "confirmed_scope_private-course": ["private-topic"],
        "active_practice_private-course": {"answers": "private answer"},
        "practice_history_private-course": {"private-session": "private history"},
        "answer_private-session_private-question": 2,
        "setup_document": {"text": "private document"},
        "tutor_result_private-course": "private tutoring answer",
    }
    for key, value in private_state.items():
        app.session_state[key] = value

    app.button(key="logout_button").click().run()

    assert_auth_gate(app)
    for key in private_state:
        assert key not in app.session_state
    assert "auth_started_at" not in app.session_state

    second_user = AuthUser(
        user_id="22222222-2222-4222-8222-222222222222",
        username="anotherstudent",
    )
    login = Mock(
        return_value=AuthResult(success=True, user=second_user, message="Signed in.")
    )
    monkeypatch.setattr(auth_ui, "login_user", login)
    submit_login(app, second_user.username)

    assert not app.exception
    assert app.session_state["auth_user"] == second_user
    assert "private-course" not in [
        course.course_id for course in app.session_state["courses"]
    ]
    for key in private_state.keys() - {"courses", "current_course"}:
        assert key not in app.session_state


def test_expired_authenticated_session_returns_to_account_gate() -> None:
    app = signed_in_app(APP_PATH)
    app.session_state["auth_started_at"] = time.time() - 9 * 60 * 60
    app.session_state["setup_document"] = {"text": "private document"}
    app.session_state["active_practice_private-course"] = {"answer": 1}

    app.run()

    assert_auth_gate(app)
    assert "auth_started_at" not in app.session_state
    assert "setup_document" not in app.session_state
    assert "active_practice_private-course" not in app.session_state
