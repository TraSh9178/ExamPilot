"""Course-scoped, browser-session state for the floating Tutor.

The client submits questions, never course content or a model configuration.
Each request uses the trusted server-side StudyPackage through ask_tutor;
displaying previous questions does not give the model conversation memory.
"""

from collections.abc import MutableMapping
from typing import Any, Callable
from uuid import uuid4

from models.schemas import StudyPackage
from services.gemini_service import MAX_TUTOR_QUESTION_CHARS, ask_tutor


ASSISTANT_STATE_KEY = "_floating_tutor_assistant"
MAX_HISTORY_MESSAGES = 20
MAX_REQUEST_ID_CHARS = 128
MAX_ANSWER_CHARS = 20_000
UNAVAILABLE_MESSAGE = "The AI tutor is unavailable right now. Please try again later."

_ERROR_MESSAGES = {
    "MISSING_API_KEY": "The AI tutor is not configured yet. Please contact your instructor or site administrator.",
    "INVALID_PACKAGE": "This course cannot be used by the tutor. Please reopen the course and try again.",
    "INVALID_QUESTION": "Please enter a text question.",
    "EMPTY_QUESTION": "Please enter a question before sending.",
    "QUESTION_TOO_LONG": "Please keep your question within 4,000 characters.",
    "INVALID_TOPIC": "The selected topic is no longer available. Please reopen the course.",
    "EMPTY_COURSE_CONTEXT": "This course has no topic summaries yet. Add course content before asking the tutor.",
    "COURSE_CONTEXT_TOO_LONG": "This course is too large for the tutor. Please ask from a smaller course.",
    "GENERATION_ERROR": UNAVAILABLE_MESSAGE,
    "EMPTY_RESPONSE": "The AI tutor returned no answer. Please try again.",
}


def initialize_assistant(session_state: MutableMapping[str, Any]) -> dict:
    """Create one assistant session without modifying learning records."""
    if ASSISTANT_STATE_KEY not in session_state:
        session_state[ASSISTANT_STATE_KEY] = {
            "session_id": str(uuid4()),
            "conversations": {},
            "seen_request_ids": set(),
        }
    return session_state[ASSISTANT_STATE_KEY]


def _saved_course_ids(session_state: MutableMapping[str, Any]) -> set[str] | None:
    courses = session_state.get("courses")
    if not isinstance(courses, list):
        return None
    return {course.course_id for course in courses if isinstance(course, StudyPackage)}


def _prune_deleted_courses(session_state: MutableMapping[str, Any], state: dict) -> None:
    saved_ids = _saved_course_ids(session_state)
    if saved_ids is not None:
        for course_id in list(state["conversations"]):
            if course_id not in saved_ids:
                del state["conversations"][course_id]


def _new_conversation() -> dict:
    return {
        "messages": [],
        "last_request_id": None,
        "error": None,
        "pending_request_id": None,
    }


def _conversation(state: dict, course_id: str) -> dict:
    return state["conversations"].setdefault(course_id, _new_conversation())


def assistant_view(
    session_state: MutableMapping[str, Any], course: StudyPackage | None
) -> dict:
    """Return only JSON-compatible presentation data, never credentials."""
    state = initialize_assistant(session_state)
    _prune_deleted_courses(session_state, state)
    saved_ids = _saved_course_ids(session_state)
    available = course is not None and (
        saved_ids is None or course.course_id in saved_ids
    )
    conversation = (
        _conversation(state, course.course_id) if available else _new_conversation()
    )
    return {
        "session_id": state["session_id"],
        "course_id": course.course_id if available else None,
        "course_name": course.course_name if available else None,
        "messages": [dict(message) for message in conversation["messages"]],
        "last_request_id": conversation["last_request_id"],
        "error": conversation["error"],
        "pending": conversation["pending_request_id"] is not None,
        "max_question_chars": MAX_TUTOR_QUESTION_CHARS,
    }


def _accept_event(
    session_state: MutableMapping[str, Any],
    state: dict,
    course: StudyPackage | None,
    event: Any,
) -> bool:
    if course is None or not isinstance(event, dict):
        return False
    saved_ids = _saved_course_ids(session_state)
    if saved_ids is not None and course.course_id not in saved_ids:
        return False
    request_id = event.get("request_id")
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or len(request_id) > MAX_REQUEST_ID_CHARS
        or event.get("course_id") != course.course_id
        or request_id in state["seen_request_ids"]
    ):
        return False
    return True


def _error_message(response: dict) -> str:
    error_code = response.get("error_code")
    if error_code == "API_ERROR":
        if response.get("status_code") == 429:
            return "The AI tutor is receiving too many requests. Please wait a moment and try again."
        if response.get("status_code") == 503:
            return UNAVAILABLE_MESSAGE
    return (
        _ERROR_MESSAGES.get(error_code, UNAVAILABLE_MESSAGE)
        if isinstance(error_code, str)
        else UNAVAILABLE_MESSAGE
    )


def submit_question(
    session_state: MutableMapping[str, Any],
    course: StudyPackage | None,
    event: Any,
    *,
    tutor: Callable[[dict, str], dict] | None = None,
) -> bool:
    """Handle an explicit submit once. False means an ignored event.

Invalid question text is acknowledged with a safe validation error. A stale
course, duplicate request, or concurrent request never contacts the model.
"""
    state = initialize_assistant(session_state)
    _prune_deleted_courses(session_state, state)
    if not _accept_event(session_state, state, course, event):
        return False
    conversation = _conversation(state, course.course_id)
    if conversation["pending_request_id"] is not None:
        return False

    request_id = event["request_id"]
    state["seen_request_ids"].add(request_id)
    conversation["last_request_id"] = request_id
    conversation["error"] = None
    question = event.get("question")
    if not isinstance(question, str):
        conversation["error"] = _ERROR_MESSAGES["INVALID_QUESTION"]
        return True
    if not question.strip():
        conversation["error"] = _ERROR_MESSAGES["EMPTY_QUESTION"]
        return True
    if len(question) > MAX_TUTOR_QUESTION_CHARS:
        conversation["error"] = _ERROR_MESSAGES["QUESTION_TOO_LONG"]
        return True

    question = question.strip()
    conversation["pending_request_id"] = request_id
    conversation["messages"].append({"role": "user", "content": question})
    try:
        response = (tutor or ask_tutor)(course.model_dump(), question)
        if not isinstance(response, dict):
            response = {"ok": False}
    except Exception:
        response = {"ok": False}

    # Finalize using the captured plain dictionaries. Streamlit session access
    # is a yield point and can interrupt this callback when navigation is queued,
    # stranding an otherwise completed answer and its pending flag. Clear or
    # deletion replaces/removes the conversation, so its response is discarded.
    # Logout removes the whole state; updating its orphaned dict cannot put it
    # back into the new user's session.
    if state["conversations"].get(course.course_id) is not conversation:
        return True

    answer = response.get("answer")
    if response.get("ok") is True and isinstance(answer, str) and answer.strip():
        content = answer.strip()
        if len(content) > MAX_ANSWER_CHARS:
            content = content[:MAX_ANSWER_CHARS] + "\n\nResponse shortened. Ask a more specific question for more detail."
        message = {"role": "assistant", "content": content}
    else:
        message = {"role": "error", "content": _error_message(response)}
    conversation["messages"].append(message)
    conversation["messages"] = conversation["messages"][-MAX_HISTORY_MESSAGES:]
    conversation["pending_request_id"] = None
    return True


def clear_conversation(
    session_state: MutableMapping[str, Any],
    course: StudyPackage | None,
    event: Any,
) -> bool:
    """Clear only the current course's local chat, retaining request deduplication."""
    state = initialize_assistant(session_state)
    _prune_deleted_courses(session_state, state)
    if not _accept_event(session_state, state, course, event):
        return False
    state["seen_request_ids"].add(event["request_id"])
    state["conversations"][course.course_id] = {
        **_new_conversation(),
        "last_request_id": event["request_id"],
    }
    return True
