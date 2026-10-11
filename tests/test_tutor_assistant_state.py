from unittest.mock import Mock

import pytest

from models.schemas import StudyPackage
from services.tutor_assistant_state import (
    ASSISTANT_STATE_KEY,
    MAX_HISTORY_MESSAGES,
    UNAVAILABLE_MESSAGE,
    assistant_view,
    clear_conversation,
    initialize_assistant,
    submit_question,
)


def make_course(course_id="calculus", name="Calculus I"):
    return StudyPackage(
        course_id=course_id,
        course_name=name,
        topics=[{"id": "limits", "name": "Limits", "summary": "A limit describes the value a function approaches."}],
        relationships=[],
        questions=[],
    )


def question_event(request_id="request-1", course_id="calculus", question="What is a limit?"):
    return {"request_id": request_id, "course_id": course_id, "question": question}


def test_initialization_is_stable_and_separate_for_browser_sessions():
    first, second = {}, {}
    original = initialize_assistant(first)
    assert initialize_assistant(first) is original
    assert original["session_id"] != initialize_assistant(second)["session_id"]
    assert assistant_view(first, None) == {
        "session_id": original["session_id"],
        "course_id": None,
        "course_name": None,
        "messages": [],
        "last_request_id": None,
        "error": None,
        "pending": False,
        "max_question_chars": 4000,
    }


def test_question_calls_existing_service_with_only_trusted_course(monkeypatch):
    state, course = {}, make_course()
    tutor = Mock(return_value={"ok": True, "answer": "  A limit is an approached value.  "})
    monkeypatch.setattr("services.tutor_assistant_state.ask_tutor", tutor)
    event = {**question_event(question="  Explain limits.  "), "package": {"course_name": "Client forgery"}}

    assert submit_question(state, course, event)
    tutor.assert_called_once_with(course.model_dump(), "Explain limits.")
    view = assistant_view(state, course)
    assert view["messages"] == [
        {"role": "user", "content": "Explain limits."},
        {"role": "assistant", "content": "A limit is an approached value."},
    ]
    assert view["last_request_id"] == "request-1"
    assert not view["pending"]
    assert "package" not in view
    view["messages"][0]["content"] = "Mutated frontend snapshot"
    assert assistant_view(state, course)["messages"][0]["content"] == "Explain limits."


@pytest.mark.parametrize("event", [None, [], "question", {}, {"request_id": None}, {"request_id": []}, question_event(request_id=""), question_event(request_id=" " * 2), question_event(request_id="x" * 129)])
def test_malformed_events_do_not_call_service(event):
    state, tutor = {}, Mock()
    assert not submit_question(state, make_course(), event, tutor=tutor)
    tutor.assert_not_called()
    assert assistant_view(state, make_course())["messages"] == []


@pytest.mark.parametrize("question", [None, {}, 1, "", " \n\t", "x" * 4001])
def test_invalid_question_is_acknowledged_without_calling_service(question):
    state, course, tutor = {}, make_course(), Mock()
    event = question_event(question=question)
    assert submit_question(state, course, event, tutor=tutor)
    tutor.assert_not_called()
    view = assistant_view(state, course)
    assert view["error"]
    assert view["last_request_id"] == event["request_id"]
    assert view["messages"] == []
    assert not submit_question(state, course, event, tutor=tutor)


def test_maximum_question_length_is_accepted():
    state, course = {}, make_course()
    tutor = Mock(return_value={"ok": True, "answer": "A valid answer."})
    assert submit_question(state, course, question_event(question="x" * 4000), tutor=tutor)
    tutor.assert_called_once()


def test_no_selected_course_never_calls_service():
    state, tutor = {}, Mock()
    assert not submit_question(state, None, question_event(), tutor=tutor)
    tutor.assert_not_called()
    assert initialize_assistant(state)["conversations"] == {}


def test_stale_course_event_does_not_leak_into_current_course():
    state, first, second = {}, make_course(), make_course("python", "Python Basics")
    tutor = Mock(return_value={"ok": True, "answer": "For the first course."})
    assert submit_question(state, first, question_event(), tutor=tutor)
    assert not submit_question(state, second, question_event("stale-request"), tutor=tutor)
    assert assistant_view(state, second)["messages"] == []
    assert assistant_view(state, first)["messages"][1]["content"] == "For the first course."
    assert tutor.call_count == 1


def test_duplicates_are_rejected_across_reruns_courses_and_failed_responses():
    state, first, second = {}, make_course(), make_course("python", "Python Basics")
    tutor = Mock(return_value={"ok": False, "error_code": "MISSING_API_KEY"})
    assert submit_question(state, first, question_event(), tutor=tutor)
    assistant_view(state, first)
    assert not submit_question(state, first, question_event(), tutor=tutor)
    assert not submit_question(state, second, question_event(course_id="python"), tutor=tutor)
    tutor.assert_called_once()


@pytest.mark.parametrize("response,expected", [
    ({"ok": False, "error_code": "MISSING_API_KEY"}, "not configured"),
    ({"ok": False, "error_code": "API_ERROR", "status_code": 429}, "too many requests"),
    ({"ok": False, "error_code": "API_ERROR", "status_code": 503}, "unavailable"),
    ({"ok": False, "error_code": "EMPTY_COURSE_CONTEXT"}, "no topic summaries"),
    ({"ok": False, "error_code": "COURSE_CONTEXT_TOO_LONG"}, "too large"),
    ({"ok": False, "error_code": "EMPTY_RESPONSE"}, "no answer"),
    ({"ok": False, "error_code": ["not-a-string"]}, "unavailable"),
    ({"ok": True, "answer": " "}, "unavailable"),
    ({"ok": 1, "answer": "Not a successful result"}, "unavailable"),
    ({"ok": True, "answer": {}}, "unavailable"),
    (None, "unavailable"),
])
def test_failed_or_malformed_responses_never_look_successful_or_expose_raw_message(response, expected):
    state, course = {}, make_course()
    if isinstance(response, dict):
        response = {**response, "message": "PRIVATE_DIAGNOSTIC_SENTINEL"}
    assert submit_question(state, course, question_event(), tutor=Mock(return_value=response))
    message = assistant_view(state, course)["messages"][-1]
    assert message["role"] == "error"
    assert expected in message["content"]
    assert "PRIVATE_DIAGNOSTIC_SENTINEL" not in message["content"]


def test_unexpected_exception_is_safe_and_a_new_request_can_retry():
    state, course = {}, make_course()
    tutor = Mock(side_effect=[RuntimeError("PRIVATE_DIAGNOSTIC_SENTINEL"), {"ok": True, "answer": "Recovered."}])
    assert submit_question(state, course, question_event(), tutor=tutor)
    assert assistant_view(state, course)["messages"][-1] == {"role": "error", "content": UNAVAILABLE_MESSAGE}
    assert submit_question(state, course, question_event("retry-2"), tutor=tutor)
    assert assistant_view(state, course)["messages"][-1] == {"role": "assistant", "content": "Recovered."}


def test_clear_only_removes_current_course_and_keeps_deduplication():
    state, first, second = {}, make_course(), make_course("python", "Python Basics")
    tutor = Mock(return_value={"ok": True, "answer": "An answer."})
    submit_question(state, first, question_event(), tutor=tutor)
    submit_question(state, second, question_event("python-1", "python"), tutor=tutor)
    clear_event = {"request_id": "clear-1", "course_id": "calculus"}
    assert clear_conversation(state, first, clear_event)
    assert assistant_view(state, first)["messages"] == []
    assert len(assistant_view(state, second)["messages"]) == 2
    assert assistant_view(state, first)["last_request_id"] == "clear-1"
    assert not clear_conversation(state, first, clear_event)
    assert not submit_question(state, first, question_event(), tutor=tutor)
    assert not clear_conversation(state, second, {"request_id": "stale-clear", "course_id": "calculus"})
    assert len(assistant_view(state, second)["messages"]) == 2


def test_chat_history_is_bounded_without_sending_old_chat_to_service():
    state, course = {}, make_course()
    tutor = Mock(return_value={"ok": True, "answer": "Answer."})
    for number in range(15):
        submit_question(state, course, question_event(f"request-{number}", question=f"Question {number}"), tutor=tutor)
    view = assistant_view(state, course)
    assert len(view["messages"]) == MAX_HISTORY_MESSAGES
    assert view["messages"][0] == {"role": "user", "content": "Question 5"}
    assert tutor.call_args.args == (course.model_dump(), "Question 14")


def test_course_deletion_drops_history_and_reimport_does_not_restore_old_chat():
    first, second = make_course(), make_course("python", "Python Basics")
    state = {"courses": [first, second]}
    tutor = Mock(return_value={"ok": True, "answer": "An answer."})
    submit_question(state, first, question_event(), tutor=tutor)
    submit_question(state, second, question_event("python-1", "python"), tutor=tutor)
    state["courses"] = [second]
    assert assistant_view(state, first)["course_id"] is None
    assert "calculus" not in initialize_assistant(state)["conversations"]
    assert not submit_question(state, first, question_event("deleted-request"), tutor=tutor)
    assert len(assistant_view(state, second)["messages"]) == 2
    state["courses"].append(first)
    assert assistant_view(state, first)["messages"] == []


def test_concurrent_request_does_not_call_service_twice():
    state, course, results = {}, make_course(), []

    def slow_tutor(package, question):
        results.append(assistant_view(state, course)["pending"])
        results.append(submit_question(state, course, question_event("concurrent"), tutor=Mock()))
        return {"ok": True, "answer": "The first answer."}

    assert submit_question(state, course, question_event(), tutor=slow_tutor)
    assert results == [True, False]
    assert len(assistant_view(state, course)["messages"]) == 2


def test_completed_response_is_committed_before_navigation_can_interrupt_session_access():
    class QueuedNavigation(BaseException):
        pass

    class YieldingState(dict):
        navigation_queued = False

        def get(self, key, default=None):
            if self.navigation_queued:
                raise QueuedNavigation("Streamlit has queued a page rerun")
            return super().get(key, default)

    course = make_course()
    state = YieldingState(courses=[course])

    def completed_service(package, question):
        state.navigation_queued = True
        return {"ok": True, "answer": "The completed answer."}

    tutor = Mock(side_effect=completed_service)
    assert submit_question(state, course, question_event(), tutor=tutor)
    tutor.assert_called_once_with(course.model_dump(), "What is a limit?")

    state.navigation_queued = False
    view = assistant_view(state, course)
    assert view["messages"][-1] == {
        "role": "assistant", "content": "The completed answer."
    }
    assert not view["pending"]
    assert not submit_question(state, course, question_event(), tutor=tutor)
    assert tutor.call_count == 1


@pytest.mark.parametrize("action", ["clear", "delete", "logout"])
def test_slow_response_cannot_restore_cleared_deleted_or_logged_out_history(action):
    course = make_course()
    state = {"courses": [course]}

    def slow_tutor(package, question):
        if action == "clear":
            clear_conversation(state, course, {"request_id": "clear-running", "course_id": course.course_id})
        elif action == "delete":
            state["courses"] = []
            assistant_view(state, None)
        else:
            del state[ASSISTANT_STATE_KEY]
        return {"ok": True, "answer": "A stale answer that must not reappear."}

    assert submit_question(state, course, question_event(), tutor=slow_tutor)
    assert assistant_view(state, course)["messages"] == []
