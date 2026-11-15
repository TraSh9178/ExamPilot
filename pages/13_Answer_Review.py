"""Review answers: the result open on the practice page, one question per screen.

Everything about a question is on the page without a click: the answer and the
correct answer, hints used, the explanation, the original wording, the reflection
and the source text.
"""
from services.i18n import tr
import streamlit as st

from components.page_links import back_button
from services.accessibility import display_question
from services.hints import hints_for
from services.practice_insights import session_insights
from services.practice_insights_ui import answer_evidence, reflection_controls
from services.practice_pages_ui import PRACTICE_PAGE, page_turn_key, render_question_heading
from services.question_review import question_sources
from services.ui_style import apply_app_styles


def review_positions(course_id):
    """Where the student is in each session's review: {session id: {"index", "turns", "move"}}."""
    return st.session_state.setdefault(f"review_position_{course_id}", {})


def move_review(course_id, session_id, step, size):
    """Previous / Next: one question, never out of range (a late click changes nothing)."""
    position = review_positions(course_id).setdefault(session_id, {"index": 0, "turns": 0})
    current = max(0, min(position.get("index", 0), size - 1))
    target = max(0, min(size - 1, current + step))
    if target == current:
        return
    position["index"] = target
    # Read once by the next render: it names the page turn.
    position["move"] = "next" if step > 0 else "prev"
    position["turns"] = position.get("turns", 0) + 1


def render_answer(review, display):
    """Your answer and the correct answer, worded and coloured as on the result screen before."""
    selected_index = review["selected_index"]
    correct_answer = display.options[review["correct_index"]]
    if selected_index is None:
        st.warning(tr("Unanswered"))
        st.success(tr(f"✓ Correct answer: {correct_answer}"))
    else:
        selected_answer = display.options[selected_index]
        if review["is_correct"]:
            st.success(tr(f"✓ Your answer: {selected_answer}"))
        else:
            st.error(tr(f"✕ Your answer: {selected_answer}"))
            st.success(tr(f"✓ Correct answer: {correct_answer}"))


apply_app_styles()

back_button(tr("Back to result"), PRACTICE_PAGE, key="review_answers_back")
st.title(tr("Review answers"))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard to start studying."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

practice_key = f"active_practice_{course.course_id}"
active = st.session_state.get(practice_key)

if active is not None and "result" not in active:
    # A new session is open (for example after "Try a different structure"): answer it there.
    st.switch_page(PRACTICE_PAGE)
    st.stop()

if active is None:
    st.caption(tr("No result to review yet. Finish a practice session first."))
    st.stop()

session, questions, result = active["session"], active["questions"], active["result"]
reviews = result["question_results"]
questions_by_id = {question.id: question for question in questions}
confirmed_topic_ids = st.session_state.get(f"confirmed_scope_{course.course_id}") or []

position = review_positions(course.course_id).setdefault(session.session_id, {"index": 0, "turns": 0})
index = position["index"] = max(0, min(position.get("index", 0), len(reviews) - 1))
review = reviews[index]
question = questions_by_id[review["question_id"]]
display = display_question(course.course_id, question, st.session_state)

st.caption(tr("Question") + f" {index + 1:02} / {len(reviews):02}")

turn_key = page_turn_key(position.pop("move", None), position.get("turns", 0), session.session_id)
with st.container(key=turn_key), st.container(key=f"review_card_{question.id}"):
    render_question_heading(index + 1, display.question)
    if display.simplified:
        st.caption(tr("Simplified wording"))
        st.subheader(tr("Original wording"))
        st.write(question.question)
        for option in question.options:
            st.write(option)

    st.subheader(tr("Answer"))
    render_answer(review, display)
    if session.mode == "topic" and (hints := hints_for(question)):
        shown = session_insights(course, session.session_id).get(question.id, {}).get("hints_used")
        if shown is not None:
            st.caption(tr(f"Hints used: {shown} of {len(hints)}"))
    answer_evidence(course, session, question)

    with st.container(border=True, key="review_explanation"):
        st.subheader(tr("Explanation"))
        st.write(display.explanation)

    reflection_controls(course, session, question, review, confirmed_topic_ids, practice_key)

    if question.source_pages:
        st.subheader(tr("Source material"))
        st.caption(tr("Cited pages: ") + ", ".join(map(str, question.source_pages)))
        for page, text in question_sources(question, st.session_state.get(f"course_document_{course.course_id}")):
            st.caption(tr(f"Page / slide {page}"))
            st.text(text, width="stretch")

with st.container(
    horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
    key="review_nav",
):
    st.button(
        tr("Previous"), icon=":material/arrow_back:", disabled=index == 0,
        key=f"review_previous_{session.session_id}",
        on_click=move_review, args=(course.course_id, session.session_id, -1, len(reviews)),
    )
    st.button(
        tr("Next"), icon=":material/arrow_forward:", icon_position="right", type="primary",
        disabled=index == len(reviews) - 1,
        key=f"review_next_{session.session_id}",
        on_click=move_review, args=(course.course_id, session.session_id, 1, len(reviews)),
    )
