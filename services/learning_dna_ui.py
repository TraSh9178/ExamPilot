"""Render evidence dimensions alongside the existing Progress statistics."""

from services.i18n import tr
import streamlit as st

from components.progress_charts import dna_rows, render_bar_chart
from services.learning_dna import DIMENSIONS, comparison, evidence_profile

# The answers behind each topic's bars have a page of their own.
EVIDENCE_PAGE = "pages/12_Learning_Evidence.py"


def evidence_topic_key(course_id):
    """Session key for the topic whose "View answers" button was clicked last."""
    return f"learning_evidence_topic_{course_id}"


def profile_inputs(course, history):
    """Attempts, sessions in saved chronological order and questions, as Progress reads them."""
    order = course.learning_state.get("session_order", [])
    ordered_ids = [sid for sid in order if sid in history]
    ordered_ids.extend(sid for sid in history if sid not in ordered_ids)
    attempts = [attempt for record in history.values() for attempt in record["attempts"]]
    questions = {question.id: question for question in course.questions}
    for record in history.values():
        for question in record["questions"]:
            questions[question.id] = question
    return attempts, [history[sid]["session"] for sid in ordered_ids], list(questions.values())


def evidence_rows(course, items):
    """The evidence table for one topic: one row per latest answer, dimension by dimension."""
    insights = course.learning_state.get("practice_insights", {})
    rows = []
    for item in items:
        for row in item.evidence if item else []:
            saved = insights.get(row['session_id'], {}).get(row['question_id'], {})
            hints = saved.get("hints_used")
            rows.append({
                tr("Dimension"): tr(DIMENSIONS[item.dimension]), tr("Question"): row['question'],
                tr("Latest answer"): tr("Correct") if row['correct'] else tr("Incorrect"),
                # A saved "not recorded" (None) reads the same as a missing entry. Counts
                # are written as text so the column holds one type.
                tr("In-app hints shown"): tr("Not recorded") if hints is None else str(hints),
                tr("Confidence"): tr({"sure": "Sure", "unsure": "Unsure", "guessed": "Guessed"}.get(saved.get("confidence"), "Not recorded")),
            })
    return rows


def evidence_tables(course, history, mode):
    """(topic, evidence rows) for each topic with evidence in this mode, in course order.

    Raises ValueError when the history cannot be read, like evidence_profile.
    """
    profile, _excluded = evidence_profile(*profile_inputs(course, history), mode)
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    tables = []
    for topic in course.topics:
        rows = evidence_rows(course, [by_key.get((topic.id, dimension)) for dimension in DIMENSIONS])
        if rows:
            tables.append((topic, rows))
    return tables


def _remember_topic(course_id, topic_id):
    """Runs on the click, before the page is drawn again: note the topic, keep the mode.

    Streamlit forgets a widget's value once the page that drew it is left;
    setting the key again here, before any widget exists, carries the chosen
    mode over to the evidence page, which uses the same key.
    """
    st.session_state[evidence_topic_key(course_id)] = topic_id
    mode_key = f"performance_mode_{course_id}"
    if mode_key in st.session_state:
        st.session_state[mode_key] = st.session_state[mode_key]


def _view_answers_button(course, topic):
    """A small button on the right edge that opens this topic's answers on their own page."""
    key = f"learning_evidence_open_{topic.id}"
    with st.container(horizontal=True, horizontal_alignment="right", key=f"page_link_{key}"):
        if st.button(tr("View answers"), key=key, icon=":material/fact_check:",
                     on_click=_remember_topic, args=(course.course_id, topic.id)):
            st.switch_page(EVIDENCE_PAGE)


def render_learning_dna(course, attempts, sessions, questions, mode, *, example=False):
    """Two labelled bars per topic, shown without a click.

    The answers behind them open on a page of their own from a small button.
    With ``example`` the numbers are sample data: the heading says so and
    there are no answers to open.
    """
    title = f"{tr('Example')} · {tr('Learning DNA')}" if example else tr("Learning DNA")
    st.subheader(title)
    st.caption(tr("See computation and conceptual understanding separately, with the answers behind each pattern."))
    st.caption(tr("How to read this profile") + " · " + tr("These are question-based observations, not a validated cognitive diagnosis. Multiple-choice answers do not demonstrate that you can explain an idea in your own words."))
    try:
        profile, _excluded = evidence_profile(attempts, sessions, questions, mode)
    except ValueError:
        st.warning(tr("Learning DNA couldn't read this practice history."))
        return
    st.caption(tr("Uses your latest answer to each question. Fewer than 3 different questions shows as insufficient evidence."))
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    # One block around the topic cards: the stylesheet sets them side by side on a wide page.
    with st.container(key="learning_dna_cards"):
        for topic in course.topics:
            pair = {dimension: by_key.get((topic.id, dimension)) for dimension in DIMENSIONS}
            with st.container(border=True, key=f"learning_dna_{topic.id}"):
                render_bar_chart(title, dna_rows(pair, tr), kind="dna", heading=topic.name)
                if all(pair.values()):
                    st.write(tr(comparison(*pair.values())))
                else:
                    st.write(tr("Answer more different questions in both dimensions before comparing them."))
                if not example and any(item is not None and item.evidence for item in pair.values()):
                    _view_answers_button(course, topic)
