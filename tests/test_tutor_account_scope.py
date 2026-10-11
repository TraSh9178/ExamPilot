"""Auth session integration with synthetic identities; no account/database calls."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models.schemas import StudyPackage
from services import tutor_assistant_ui
from services.auth_service import AuthUser
from services.auth_session import (
    SESSION_DURATION_SECONDS,
    current_user,
    logout_session,
    start_authenticated_session,
)
from services.tutor_assistant_state import (
    ASSISTANT_STATE_KEY,
    assistant_view,
    clear_conversation,
    submit_question,
)


NOW = 1_000_000.0
USER_A = AuthUser("11111111-1111-4111-8111-111111111111", "student_a")
USER_B = AuthUser("22222222-2222-4222-8222-222222222222", "student_b")


@pytest.fixture(autouse=True)
def fixed_auth_clock(monkeypatch):
    monkeypatch.setattr("services.auth_session.time.time", lambda: NOW)


def make_course():
    return StudyPackage(
        course_id="same-demo",
        course_name="Microeconomics Demo",
        topics=[{"id": "demand", "name": "Demand", "summary": "Demand relates price to quantity demanded."}],
        relationships=[],
        questions=[],
    )


def signed_in_state(user=USER_A):
    state = {}
    start_authenticated_session(state, user)
    course = make_course()
    state.update(courses=[course], current_course=course)
    return state, course


def event_for(view, request_id="question-1", question="Explain demand."):
    return {
        "request_id": request_id,
        "session_id": view["session_id"],
        "course_id": view["course_id"],
        "question": question,
    }


def mount_ui(monkeypatch, state):
    mounted = Mock()
    factory = Mock(return_value=mounted)
    monkeypatch.setattr(tutor_assistant_ui, "st", SimpleNamespace(session_state=state))
    monkeypatch.setattr(tutor_assistant_ui, "_component", factory)
    tutor_assistant_ui.render_tutor_assistant()
    return factory, mounted


@pytest.mark.parametrize("auth_state", ["missing", "expired", "untrusted", "invalid_id"])
def test_unauthenticated_or_expired_ui_does_not_mount_or_call_tutor(monkeypatch, auth_state):
    state, course = signed_in_state()
    if auth_state == "missing":
        logout_session(state)
    elif auth_state == "expired":
        state["auth_started_at"] = NOW - SESSION_DURATION_SECONDS
    elif auth_state == "untrusted":
        state["auth_user"] = {"user_id": USER_A.user_id}
    else:
        state["auth_user"] = AuthUser("", "invalid")
    tutor = Mock()
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)

    factory, mounted = mount_ui(monkeypatch, state)
    factory.assert_not_called()
    mounted.assert_not_called()
    tutor.assert_not_called()
    assert ASSISTANT_STATE_KEY not in state


def test_authenticated_ui_mount_is_owned_by_server_identity_without_calling_tutor(monkeypatch):
    state, course = signed_in_state()
    tutor = Mock()
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)

    factory, mounted = mount_ui(monkeypatch, state)
    factory.assert_called_once_with()
    assert state[ASSISTANT_STATE_KEY]["owner_id"] == current_user(state).user_id
    assert mounted.call_args.kwargs["data"]["course_id"] == course.course_id
    assert "owner_id" not in mounted.call_args.kwargs["data"]
    tutor.assert_not_called()


def test_logged_out_cleanup_has_no_chat_html_events_or_service_call(monkeypatch):
    state = {}
    mounted = Mock()
    register = Mock(return_value=mounted)
    tutor_factory = Mock()
    tutor = Mock()
    monkeypatch.setattr(tutor_assistant_ui, "st", SimpleNamespace(session_state=state))
    monkeypatch.setattr(tutor_assistant_ui.components, "component", register)
    monkeypatch.setattr(tutor_assistant_ui, "_component", tutor_factory)
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)
    tutor_assistant_ui._cleanup_component.cache_clear()
    try:
        tutor_assistant_ui.clear_tutor_browser_state()
    finally:
        tutor_assistant_ui._cleanup_component.cache_clear()

    assert register.call_args.args == ("exampilot_tutor_session_cleanup",)
    definition = register.call_args.kwargs
    assert set(definition) == {"js"}
    assert "window.__examPilotFloatingTutor.reset()" in definition["js"]
    assert "delete window.__examPilotFloatingTutor" in definition["js"]
    assert "setTriggerValue" not in definition["js"]
    mounted.assert_called_once_with(
        key="floating_tutor_session_cleanup", width="stretch", height=1
    )
    tutor_factory.assert_not_called()
    tutor.assert_not_called()
    assert state == {}


@pytest.mark.parametrize("callback_name", ["on_submit_change", "on_clear_change"])
@pytest.mark.parametrize("auth_state", ["logout", "expired"])
def test_stale_callbacks_after_logout_or_expiry_do_not_call_service(monkeypatch, callback_name, auth_state):
    state, course = signed_in_state()
    factory, mounted = mount_ui(monkeypatch, state)
    callbacks = mounted.call_args.kwargs
    old_event = event_for(callbacks["data"])
    if auth_state == "logout":
        logout_session(state)
    else:
        state["auth_started_at"] = NOW - SESSION_DURATION_SECONDS
    state[tutor_assistant_ui.COMPONENT_KEY] = {"submit": old_event, "clear": old_event}
    tutor = Mock()
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)

    callbacks[callback_name]()
    tutor.assert_not_called()
    assert ASSISTANT_STATE_KEY not in state
    assert current_user(state) is None


def test_real_auth_session_start_logout_then_second_account_has_no_old_chat():
    state, course = signed_in_state()
    first_view = assistant_view(state, course, owner_id=current_user(state).user_id)
    tutor = Mock(return_value={"ok": True, "answer": "Account A's local answer."})
    assert submit_question(state, course, event_for(first_view), owner_id=USER_A.user_id, tutor=tutor)

    logout_session(state)
    assert state == {}
    start_authenticated_session(state, USER_B)
    state.update(courses=[course], current_course=course)
    second_view = assistant_view(state, course, owner_id=current_user(state).user_id)
    assert second_view["messages"] == []
    assert second_view["session_id"] != first_view["session_id"]
    assert not submit_question(state, course, event_for(first_view, "stale-after-login"), owner_id=USER_B.user_id, tutor=tutor)
    assert tutor.call_count == 1


def test_owner_change_without_full_clear_replaces_chat_and_rejects_old_session_token():
    state, course = signed_in_state()
    first_view = assistant_view(state, course, owner_id=USER_A.user_id)
    tutor = Mock(return_value={"ok": True, "answer": "Only for A."})
    submit_question(state, course, event_for(first_view), owner_id=USER_A.user_id, tutor=tutor)

    state["auth_user"] = USER_B
    second_view = assistant_view(state, course, owner_id=current_user(state).user_id)
    assert second_view["session_id"] != first_view["session_id"]
    assert second_view["messages"] == []
    assert state[ASSISTANT_STATE_KEY]["owner_id"] == USER_B.user_id
    assert not submit_question(state, course, event_for(first_view, "stale-submit"), owner_id=USER_B.user_id, tutor=tutor)
    assert not clear_conversation(state, course, event_for(first_view, "stale-clear"), owner_id=USER_B.user_id)
    assert tutor.call_count == 1


@pytest.mark.parametrize("token", [None, "", "previous-session", 3, {}])
def test_owner_bound_requests_require_matching_session_token(token):
    state, course = signed_in_state()
    view = assistant_view(state, course, owner_id=USER_A.user_id)
    tutor = Mock()
    event = {**event_for(view), "session_id": token}
    assert not submit_question(state, course, event, owner_id=USER_A.user_id, tutor=tutor)
    assert not clear_conversation(state, course, event, owner_id=USER_A.user_id)
    tutor.assert_not_called()
    assert assistant_view(state, course, owner_id=USER_A.user_id)["messages"] == []


def test_callback_checks_current_user_and_rejects_previous_accounts_event(monkeypatch):
    state, course = signed_in_state()
    factory, mounted = mount_ui(monkeypatch, state)
    callbacks = mounted.call_args.kwargs
    first_view = callbacks["data"]
    state["auth_user"] = USER_B
    state[tutor_assistant_ui.COMPONENT_KEY] = {"submit": event_for(first_view)}
    tutor = Mock(return_value={"ok": True, "answer": "For B only."})
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)

    callbacks["on_submit_change"]()
    tutor.assert_not_called()
    second_view = assistant_view(state, course, owner_id=USER_B.user_id)
    assert second_view["messages"] == []
    assert second_view["session_id"] != first_view["session_id"]

    state[tutor_assistant_ui.COMPONENT_KEY] = {"submit": event_for(second_view, "b-question")}
    callbacks["on_submit_change"]()
    tutor.assert_called_once_with(course.model_dump(), "Explain demand.")
    assert assistant_view(state, course, owner_id=USER_B.user_id)["messages"][-1]["content"] == "For B only."
    state[tutor_assistant_ui.COMPONENT_KEY] = {"clear": event_for(first_view, "stale-clear")}
    callbacks["on_clear_change"]()
    assert len(assistant_view(state, course, owner_id=USER_B.user_id)["messages"]) == 2


def test_same_account_restored_course_object_keeps_its_current_session_chat():
    state, course = signed_in_state()
    first_view = assistant_view(state, course, owner_id=USER_A.user_id)
    tutor = Mock(return_value={"ok": True, "answer": "An answer kept locally."})
    submit_question(state, course, event_for(first_view), owner_id=USER_A.user_id, tutor=tutor)
    restored = StudyPackage.model_validate(course.model_dump())
    assert restored is not course
    state.update(courses=[restored], current_course=restored)

    restored_view = assistant_view(state, restored, owner_id=current_user(state).user_id)
    assert restored_view["session_id"] == first_view["session_id"]
    assert restored_view["messages"][-1]["content"] == "An answer kept locally."
    assert tutor.call_count == 1


@pytest.mark.parametrize("switch", ["owner_change", "logout_and_login"])
def test_delayed_old_answer_cannot_appear_for_new_account(switch):
    state, course = signed_in_state()
    first_view = assistant_view(state, course, owner_id=USER_A.user_id)

    def slow_tutor(package, question):
        if switch == "logout_and_login":
            logout_session(state)
            start_authenticated_session(state, USER_B)
            state.update(courses=[course], current_course=course)
        else:
            state["auth_user"] = USER_B
        assistant_view(state, course, owner_id=current_user(state).user_id)
        return {"ok": True, "answer": "A stale answer from A."}

    assert submit_question(state, course, event_for(first_view), owner_id=USER_A.user_id, tutor=slow_tutor)
    second_view = assistant_view(state, course, owner_id=current_user(state).user_id)
    assert second_view["messages"] == []
    assert second_view["session_id"] != first_view["session_id"]
    assert not second_view["pending"]
