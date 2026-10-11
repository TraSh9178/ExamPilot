"""Save and restore the signed-in account's study data for the UI session.

Identity always comes from the trusted login session. Without a signed-in
user every function is a local-only no-op, so anonymous data is never
written to or migrated into an account.
"""

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

import streamlit as st

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services import postgres_store
from services.auth_session import current_user
from services.course_state import initialize_courses
from services.exam_engine import grade_exam
from services.ui_adapters import PENDING_INTEGRATION_MESSAGES

STATE_KEY = "account_sync"


@dataclass(frozen=True)
class SyncOutcome:
    success: bool
    message: str


def _user_id(session_state: MutableMapping[str, Any]) -> str | None:
    user = current_user(session_state)
    return user.user_id if user is not None else None


def _state(session_state: MutableMapping[str, Any], user_id: str) -> dict:
    state = session_state.get(STATE_KEY)
    if state is None or state.get("user_id") != user_id:
        state = {
            "user_id": user_id,
            "restore_attempted": False,
            "restore_errors": [],
            "restore_message": "",
            "unsaved_courses": set(),
            "unsaved_exams": set(),
            "course_messages": {},
            "last_save": None,
        }
        session_state[STATE_KEY] = state
    return state


def _history_key(course_id: str) -> str:
    return f"practice_history_{course_id}"


def _apply_restored_course(
    session_state: MutableMapping[str, Any],
    state: dict,
    restored: postgres_store.CourseHistoryResult,
) -> None:
    """Database records replace same-ID local copies; the current course stays."""
    package = restored.package
    initialize_courses(session_state)
    courses = session_state["courses"]
    for index, course in enumerate(courses):
        if course.course_id == package.course_id:
            courses[index] = package
            break
    else:
        courses.append(package)

    current = session_state.get("current_course")
    if current is not None and current.course_id == package.course_id:
        session_state["current_course"] = package

    questions_by_id = {question.id: question for question in package.questions}
    answers_by_session: dict[str, dict[str, int | None]] = {}
    for attempt in restored.attempts:
        answers_by_session.setdefault(attempt.session_id, {})[
            attempt.question_id
        ] = attempt.selected_index

    history = session_state.setdefault(_history_key(package.course_id), {})
    for session in restored.sessions:
        questions = [questions_by_id[qid] for qid in session.question_ids]
        result = grade_exam(
            session, questions, answers_by_session.get(session.session_id, {})
        )
        history[session.session_id] = {
            "session": session,
            "questions": questions,
            "attempts": result["attempts"].copy(),
            "result": result,
        }
        state["unsaved_exams"].discard((package.course_id, session.session_id))

    state["unsaved_courses"].discard(package.course_id)


def _restore_one(
    session_state: MutableMapping[str, Any],
    state: dict,
    user_id: str,
    course_id: str,
    label: str,
) -> str | None:
    """Restore one course; return an error text, or None on success."""
    restored = postgres_store.load_course_history(user_id, course_id)
    if not restored.success or restored.package is None:
        reason = restored.message if not restored.success else "Course was not found."
        return f"{label}: {reason}"
    try:
        _apply_restored_course(session_state, state, restored)
    except (KeyError, ValueError):
        return f"{label}: Stored exam data could not be matched to its questions."
    return None


def restore_all(session_state: MutableMapping[str, Any]) -> SyncOutcome | None:
    """List this account's courses, then restore each one's history."""
    user_id = _user_id(session_state)
    if user_id is None:
        return None
    state = _state(session_state, user_id)
    state["restore_attempted"] = True

    listing = postgres_store.list_saved_courses(user_id)
    if not listing.success:
        state["restore_errors"] = [listing.message]
        state["restore_message"] = ""
        return SyncOutcome(False, listing.message)

    if not listing.courses:
        state["restore_errors"] = []
        state["restore_message"] = "No saved study records for this account yet."
        return SyncOutcome(True, state["restore_message"])

    errors = []
    restored_count = 0
    for summary in listing.courses:
        error = _restore_one(
            session_state, state, user_id, summary.course_id, summary.course_name
        )
        if error is None:
            restored_count += 1
        else:
            errors.append(error)

    state["restore_errors"] = errors
    state["restore_message"] = (
        f"Restored {restored_count} of {len(listing.courses)} saved course(s)."
    )
    return SyncOutcome(not errors, state["restore_message"])


def restore_after_login(session_state: MutableMapping[str, Any]) -> None:
    """Restore the account once per login; reruns do not query again."""
    user_id = _user_id(session_state)
    if user_id is None or _state(session_state, user_id)["restore_attempted"]:
        return
    with st.spinner("Restoring your saved study records…"):
        restore_all(session_state)


def _with_history_questions(
    session_state: MutableMapping[str, Any], course: StudyPackage,
) -> StudyPackage:
    """Keep questions that local history still references (e.g. after the
    question bank is regenerated) so the saved history stays restorable."""
    known = {q.id for q in course.questions}
    missing = []
    history = session_state.get(_history_key(course.course_id), {})
    for record in history.values():
        for question in record["questions"]:
            if question.id not in known:
                known.add(question.id)
                missing.append(question)
    if not missing:
        return course
    return course.model_copy(update={"questions": [*course.questions, *missing]})


def save_course_to_account(
    session_state: MutableMapping[str, Any], course: StudyPackage,
) -> SyncOutcome | None:
    user_id = _user_id(session_state)
    if user_id is None:
        return None
    state = _state(session_state, user_id)
    result = postgres_store.save_course(
        user_id, _with_history_questions(session_state, course)
    )
    if result.success:
        state["unsaved_courses"].discard(course.course_id)
    else:
        state["unsaved_courses"].add(course.course_id)
    outcome = SyncOutcome(result.success, result.message)
    state["last_save"] = outcome
    return outcome


def save_exam_to_account(
    session_state: MutableMapping[str, Any],
    course: StudyPackage,
    session: ExamSession,
    attempts: list[AttemptResult],
) -> SyncOutcome | None:
    """Save the course first, then the session and full answer snapshot."""
    user_id = _user_id(session_state)
    if user_id is None:
        return None
    state = _state(session_state, user_id)
    key = (course.course_id, session.session_id)

    course_outcome = save_course_to_account(session_state, course)
    if not course_outcome.success:
        state["unsaved_exams"].add(key)
        outcome = SyncOutcome(
            False,
            "Course could not be saved, so this practice result is only kept "
            f"in this session. {course_outcome.message}",
        )
        state["last_save"] = outcome
        return outcome

    result = postgres_store.save_exam_result(
        user_id, course.course_id, session, attempts
    )
    if result.success:
        state["unsaved_exams"].discard(key)
    else:
        state["unsaved_exams"].add(key)
    outcome = SyncOutcome(result.success, result.message)
    state["last_save"] = outcome
    return outcome


def save_course_with_history(
    session_state: MutableMapping[str, Any], course: StudyPackage,
) -> SyncOutcome | None:
    """Save a course and all of its local graded sessions (idempotent retry)."""
    user_id = _user_id(session_state)
    if user_id is None:
        return None
    state = _state(session_state, user_id)
    outcome = save_course_to_account(session_state, course)
    if not outcome.success:
        return outcome

    history = session_state.get(_history_key(course.course_id), {})
    for session_id, record in history.items():
        result = postgres_store.save_exam_result(
            user_id, course.course_id, record["session"], record["attempts"]
        )
        key = (course.course_id, session_id)
        if result.success:
            state["unsaved_exams"].discard(key)
        else:
            state["unsaved_exams"].add(key)
            outcome = SyncOutcome(False, result.message)
            state["last_save"] = outcome
            return outcome

    outcome = SyncOutcome(True, "Course and practice history saved to your account.")
    state["last_save"] = outcome
    return outcome


def restore_course(
    session_state: MutableMapping[str, Any], course_id: str,
) -> SyncOutcome | None:
    user_id = _user_id(session_state)
    if user_id is None:
        return None
    state = _state(session_state, user_id)
    error = _restore_one(session_state, state, user_id, course_id, course_id)
    if error is not None:
        return SyncOutcome(False, error)
    return SyncOutcome(True, "Course and practice history restored.")


def render_sidebar_status() -> None:
    """Show failed restore/save state with a retry, in the signed-in sidebar."""
    session_state = st.session_state
    user_id = _user_id(session_state)
    if user_id is None:
        return
    state = _state(session_state, user_id)

    if state["restore_errors"]:
        st.warning(
            "Some saved records could not be restored. Your current work is "
            "unchanged.\n\n" + "\n".join(f"- {e}" for e in state["restore_errors"])
        )
        if st.button("Retry restore", key="retry_restore", use_container_width=True):
            with st.spinner("Restoring your saved study records…"):
                restore_all(session_state)
            st.rerun()
    elif state["restore_message"]:
        st.caption(state["restore_message"])

    unsaved = len(state["unsaved_courses"]) + len(state["unsaved_exams"])
    if unsaved:
        st.warning(
            f"{unsaved} item(s) are not saved to your account yet. "
            "Use Save in Study Plan to retry."
        )


def render_save_restore_controls(course: StudyPackage) -> None:
    """Save/Restore buttons for one course, with explicit status text."""
    session_state = st.session_state
    user_id = _user_id(session_state)
    if user_id is None:
        st.caption(PENDING_INTEGRATION_MESSAGES["database"])
        for column, label, kind in zip(st.columns(2), ("Save", "Restore"), ("save", "restore")):
            column.button(
                label, key=f"database_{kind}_{course.course_id}",
                disabled=True, use_container_width=True,
            )
        return

    state = _state(session_state, user_id)
    message_key = course.course_id
    st.caption(
        "Saves this course and its graded practice to your account. "
        "Anonymous records from before login are not migrated."
    )
    save_column, restore_column = st.columns(2)
    save_clicked = save_column.button(
        "Save", key=f"database_save_{course.course_id}", use_container_width=True,
    )
    restore_clicked = restore_column.button(
        "Restore", key=f"database_restore_{course.course_id}",
        use_container_width=True,
    )

    if save_clicked:
        with st.spinner("Saving…"):
            outcome = save_course_with_history(session_state, course)
        state["course_messages"][message_key] = outcome
    elif restore_clicked:
        with st.spinner("Restoring…"):
            outcome = restore_course(session_state, course.course_id)
        state["course_messages"][message_key] = outcome
        if outcome.success:
            st.rerun()

    outcome = state["course_messages"].get(message_key)
    if outcome is not None:
        (st.success if outcome.success else st.error)(outcome.message)


def render_last_save_status() -> None:
    """Report the latest automatic save result; failure never reads as success."""
    user_id = _user_id(st.session_state)
    if user_id is None:
        return
    outcome = _state(st.session_state, user_id)["last_save"]
    if outcome is None:
        return
    if outcome.success:
        st.caption("Saved to your account.")
    else:
        st.warning(
            f"Not saved to your account: {outcome.message} "
            "Your local work is kept; use Save in Study Plan to retry."
        )
