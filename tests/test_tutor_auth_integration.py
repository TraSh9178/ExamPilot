"""Exercise the real app auth gate and session cleanup around the floating Tutor."""

from pathlib import Path
import time
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from services import auth_ui
from services.auth_service import AuthResult, AuthUser
from services.tutor_assistant_state import (
    ASSISTANT_STATE_KEY,
    assistant_view,
    submit_question,
)
from tests.auth_helpers import signed_in_app


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
PRIVATE_QUESTION = "Synthetic private question belonging to account A"
PRIVATE_ANSWER = "Synthetic private answer belonging to account A"


def _populate_tutor(app: AppTest) -> None:
    course = app.session_state["courses"][0]
    app.session_state["current_course"] = course
    app.run()
    assert not app.exception
    owner_id = app.session_state["auth_user"].user_id
    # AppTest exposes SafeSessionState rather than the production mapping
    # proxy. Share its existing plain Tutor dictionary with the controller.
    controller_state = {
        "courses": app.session_state["courses"],
        ASSISTANT_STATE_KEY: app.session_state[ASSISTANT_STATE_KEY],
    }
    view = assistant_view(controller_state, course, owner_id=owner_id)
    accepted = submit_question(
        controller_state,
        course,
        {
            "request_id": "synthetic-auth-private-question",
            "course_id": course.course_id,
            "session_id": view["session_id"],
            "question": PRIVATE_QUESTION,
        },
        tutor=lambda package, question: {"ok": True, "answer": PRIVATE_ANSWER},
        owner_id=owner_id,
    )
    assert accepted
    assert assistant_view(controller_state, course)["messages"][-1]["content"] == PRIVATE_ANSWER


def _assert_logged_out_tutor(app: AppTest) -> None:
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Log in", "Create account"]
    assert "auth_user" not in app.session_state
    assert ASSISTANT_STATE_KEY not in app.session_state
    assert "floating_tutor" not in app.session_state
    assert not any(button.label == "Open course" for button in app.button)


def test_logged_out_gate_does_not_initialize_the_tutor() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()
    _assert_logged_out_tutor(app)


def test_logout_clears_floating_tutor_history_and_widget() -> None:
    app = signed_in_app(APP_PATH).run()
    _populate_tutor(app)
    assert ASSISTANT_STATE_KEY in app.session_state
    app.button(key="logout_button").click().run()
    _assert_logged_out_tutor(app)


def test_expired_session_clears_tutor_before_returning_to_login() -> None:
    app = signed_in_app(APP_PATH).run()
    _populate_tutor(app)
    app.session_state["auth_started_at"] = time.time() - 9 * 60 * 60
    app.run()
    _assert_logged_out_tutor(app)


def test_second_account_using_same_demo_has_no_previous_account_chat(monkeypatch) -> None:
    app = signed_in_app(APP_PATH).run()
    _populate_tutor(app)
    app.button(key="logout_button").click().run()
    _assert_logged_out_tutor(app)

    user_b = AuthUser("22222222-2222-4222-8222-222222222222", "synthetic_account_b")
    login = Mock(return_value=AuthResult(True, user_b, "Signed in."))
    monkeypatch.setattr(auth_ui, "login_user", login)
    app.text_input(key="login_username").set_value(user_b.username)
    app.text_input(key="login_password").set_value("Synthetic test passphrase")
    next(button for button in app.button if button.label == "Log in").click().run()

    assert not app.exception
    assert app.session_state["auth_user"] == user_b
    course = app.session_state["courses"][0]
    app.session_state["current_course"] = course
    app.run()
    assert not app.exception
    view = assistant_view(
        {"courses": app.session_state["courses"], ASSISTANT_STATE_KEY: app.session_state[ASSISTANT_STATE_KEY]},
        course,
        owner_id=user_b.user_id,
    )
    assert view["messages"] == []
    assert PRIVATE_QUESTION not in repr(view)
    assert PRIVATE_ANSWER not in repr(view)
    login.assert_called_once()
