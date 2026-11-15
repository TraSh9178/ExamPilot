"""Guided review of the original Calculus I demo's factorisation question."""

from uuid import uuid4

import streamlit as st

from components.knowledge_graph import forget_course_radar
from models.schemas import ExamSession
from services import learning_radar
from services.auth_session import current_user
from services.course_state import select_course
from services.learning_flow import install_practice
from services.question_editor import available_questions
from services.i18n import tr


DEMO_COURSE_ID = "calculus-i-demo"
TOPIC_ID = "calc_limits"
QUESTION_ID = "calc_q001"
REASONS = {
    "start": ("I got 0/0 and stopped", "Try rewriting the expression before substituting again."),
    "concept": ("I didn’t see how to factor the numerator", "Look for a difference of two perfect squares."),
    "unsure": ("I’m not sure", "Start with the numerator. The denominator already has a linear factor."),
}
FACTORS = ("(x − 2)²", "(x − 2)(x + 2)", "x(x − 4)")


def starter_question(course):
    if course.course_id == DEMO_COURSE_ID:
        return next(
            (q for q in available_questions(course) if q.id == QUESTION_ID and q.topic_id == TOPIC_ID),
            None,
        )
    return None


def start_demo(state, course, question):
    scope_key = f"confirmed_scope_{course.course_id}"
    confirmed = state.get(scope_key) or [question.topic_id]
    if question.topic_id not in confirmed:
        raise ValueError("The demo question is outside the confirmed scope.")

    select_course(state, course.course_id)
    state[scope_key] = confirmed
    state[f"practice_mode_{course.course_id}"] = tr("Topic Practice")
    state[f"practice_topic_{course.course_id}"] = question.topic_id
    state[f"practice_count_{course.course_id}"] = 1
    session = ExamSession(session_id=str(uuid4()), mode="topic", question_ids=[question.id])
    install_practice(
        state,
        course.course_id,
        {
            "session": session,
            "questions": [question],
            "warning": None,
            "settings": {
                "mode": "topic",
                "requested_count": 1,
                "topic_id": question.topic_id,
                "confirmed_topic_ids": sorted(confirmed),
            },
        },
    )


def render_guided_review(course, session, questions, result) -> bool:
    if course.course_id != DEMO_COURSE_ID or session.mode != "topic":
        return False
    question = next((q for q in questions if q.id == QUESTION_ID and q.topic_id == TOPIC_ID), None)
    if question is None:
        return False
    attempt = next((item for item in result["attempts"] if item.question_id == question.id), None)
    if attempt is None or attempt.is_correct:
        return False

    key = f"guided_limits_{session.session_id}"
    progress = st.session_state.setdefault(key, {})
    first_answer = question.options[attempt.selected_index] if attempt.selected_index is not None else "Unanswered"

    with st.container(border=True, key="guided_limits_review"):
        st.subheader(tr("Redo the step that stopped you"))
        st.caption(tr("Calculus I · Limits"))
        if progress.get("complete"):
            original, follow_up = st.columns(2)
            with original:
                st.markdown(tr("**First question**"))
                st.write(tr("Your answer: ") + first_answer)
                st.caption(tr(REASONS[progress["reason"]][0]))
            with follow_up:
                st.markdown(tr("**New question**"))
                st.success(tr("8 · Correct"))
                st.caption(tr("Solved after a retry." if progress["retried"] else "Solved on your first try."))
            st.caption(tr("You practised factoring a difference of squares before taking the limit."))
            return True

        st.markdown(tr("**First answer:** ") + first_answer)
        if "reason" not in progress:
            reason = st.radio(
                tr("Where did you get stuck?"),
                list(REASONS),
                index=None,
                format_func=lambda value: tr(REASONS[value][0]),
                key=f"{key}_reason",
            )
            if st.button(tr("Work on this step"), type="primary", key=f"{key}_start"):
                if reason is None:
                    st.warning(tr("Choose what stopped you, or select I’m not sure."))
                else:
                    progress["reason"] = reason
                    st.rerun()
            return True

        st.info(tr(REASONS[progress["reason"]][1]))
        user = current_user(st.session_state)
        if user is not None and progress["reason"] in learning_radar.REASON_LABELS:
            with st.expander(tr("Learning Radar · share this blocker")):
                st.caption(tr("Add this topic and reason to the anonymous course totals."))
                if progress.get("flag_saved"):
                    st.caption(tr("Shared with Learning Radar."))
                elif st.button(tr("Share anonymously"), key=f"{key}_flag"):
                    outcome = learning_radar.set_flag(user.user_id, course.course_id, TOPIC_ID, progress["reason"])
                    if outcome.success:
                        progress["flag_saved"] = True
                        forget_course_radar(st.session_state, course.course_id)
                        st.rerun()
                    else:
                        st.warning(tr("Learning Radar is unavailable. You can still finish this review."))

        if not progress.get("step_done"):
            factor = st.radio(
                tr("Which expression equals x² − 4?"),
                FACTORS,
                index=None,
                key=f"{key}_factor",
            )
            if st.button(tr("Check this step"), type="primary", key=f"{key}_check"):
                if factor == FACTORS[1]:
                    progress["step_done"] = True
                    st.rerun()
                elif factor is None:
                    st.warning(tr("Choose an expression first."))
                else:
                    st.warning(tr("Expand your choice. Does the middle term cancel?"))
            return True

        st.markdown(tr("**The step you repaired:** x² − 4 = (x − 2)(x + 2)"))
        st.caption(tr("For x ≠ 2, cancel x − 2 and take the limit of x + 2."))
        answer = st.radio(
            tr("New question: what is limₓ→₄ (x² − 16)/(x − 4)?"),
            ("0", "4", "8", "The limit does not exist"),
            format_func=tr,
            index=None,
            key=f"{key}_transfer",
        )
        if st.button(tr("Check the new question"), type="primary", key=f"{key}_finish"):
            if answer is None:
                st.warning(tr("Choose an answer first."))
            elif answer == "8":
                progress["retried"] = progress.get("retried", False)
                progress["complete"] = True
                st.rerun()
            else:
                progress["retried"] = True
                st.warning(tr("Try rewriting x² − 16 as a difference of squares."))
    return True
