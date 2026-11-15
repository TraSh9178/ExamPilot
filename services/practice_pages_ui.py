"""What the practice page and its two focus pages (Practice history, Review answers) share.

A page script cannot import another page script, so the pieces more than one of
them needs live here: session labels, the state changes behind Resume and Open
result, the question heading and the page-turn container key.
"""
from html import escape

import streamlit as st

from services.i18n import tr
from services.learning_flow import install_practice, resume_draft

PRACTICE_PAGE = "pages/2_Practice_Center.py"
HISTORY_PAGE = "pages/8_Practice_History.py"
ANSWER_REVIEW_PAGE = "pages/13_Answer_Review.py"


def question_count(count):
    return tr("1 question") if count == 1 else tr(f"{count} questions")


def practice_label(records, sid, *, unfinished=False):
    """Human-readable choices; stable session IDs remain internal widget values."""
    record = records[sid]
    number = list(records).index(sid) + 1
    if "session" not in record:
        return f"{number} · {tr('Saved practice')}"
    mode = tr("Topic practice") if record["session"].mode == "topic" else tr("Mock exam")
    label = f"{number} · {mode} · {question_count(len(record['questions']))}"
    result = record.get("result")
    if result is not None:
        label += " · " + tr(f"{result['correct_count']}/{result['total_count']} correct")
    elif unfinished:
        label += " · " + tr("Unfinished")
    return label


def has_practice_history(state, course_id):
    """True when the course has an unfinished or a graded session to list."""
    return bool(state.get(f"practice_drafts_{course_id}")) or bool(state.get(f"practice_history_{course_id}"))


def history_visit_key(course_id):
    """Set while Practice history is open; the practice page reads it once on the way back."""
    return f"practice_history_visited_{course_id}"


def can_open_result(record):
    """A saved record that holds everything the result screen shows."""
    return isinstance(record, dict) and all(key in record for key in ("session", "questions", "result"))


def drop_pending_requests(state, course_id):
    """The student picked a session: a new-practice request from another page and a
    "Change settings" request no longer apply."""
    state.pop(f"practice_entry_{course_id}", None)
    state.pop(f"practice_setup_{course_id}", None)


def is_open(state, course_id, session_id):
    active = state.get(f"active_practice_{course_id}")
    return bool(active) and active["session"].session_id == session_id


def resume_session(state, course_id, session_id):
    """Resume an unfinished session on its question screen, where the student left it.

    A session in progress is kept as unfinished (install_practice archives it). A
    repeated click, when the session is already open, changes nothing. Returns True
    when the session is open afterwards.
    """
    if session_id in state.get(f"practice_drafts_{course_id}", {}):
        resume_draft(state, course_id, session_id)
        state[f"active_practice_{course_id}"].pop("worksheet_step", None)
    if not is_open(state, course_id, session_id):
        return False
    drop_pending_requests(state, course_id)
    return True


def open_saved_result(state, course_id, session_id):
    """Show a graded session's result screen again; nothing is graded or saved anew.

    A session in progress is kept as unfinished, with its answers, confidence and hints.
    """
    record = state.get(f"practice_history_{course_id}", {}).get(session_id)
    if not can_open_result(record):
        return False
    if not is_open(state, course_id, session_id):
        install_practice(state, course_id, {
            "session": record["session"], "questions": record["questions"], "result": record["result"],
            "warning": None, "settings": {},
        })
    drop_pending_requests(state, course_id)
    return True


def render_question_heading(number, text):
    """Paper question card: a two-digit badge beside the question text."""
    body = "<br>".join(escape(line, quote=False) for line in text.splitlines())
    st.markdown(
        f'<div class="paper-question"><span class="paper-question-badge">{escape(tr(f"Q{number:02}"))}</span>'
        f'<div class="paper-question-text">{body}</div></div>',
        unsafe_allow_html=True,
    )


def page_turn_key(move, turns, session_id):
    """Key of the container that turns like a page (see assets/paper_practice.css).

    It names the last move and alternates a/b, so the animation replays on every
    move; any rerun that kept the question renders "none", which does not animate.
    """
    if move in ("next", "prev"):
        return f"practice_turn_{move}_{'ab'[turns % 2]}_{session_id}"
    return f"practice_turn_none_{session_id}"
