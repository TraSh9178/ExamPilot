from services.ui_help import help_tip
from services.i18n import tr
import streamlit as st

from components.progress_charts import (
    mastery_rows,
    render_bar_chart,
    render_example_banner,
    render_session_chart,
    session_points,
)
from services.example_report import example_report_for
from services.mastery_engine import calculate_topic_stats
from services.ui_style import apply_app_styles
from services.learning_dna_ui import render_learning_dna
from services.practice_insights_ui import render_history_insights


apply_app_styles()

st.title(tr("Progress"))
help_tip(tr("Review practice results and see which topics need more evidence."))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

with st.container(key="progress_course_heading"):
    st.subheader(course.course_name)

history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

# A built-in demo course with no graded session yet shows a labelled example.
# It lives in these local variables only and disappears with the first real session.
example = example_report_for(course, history)
report_course = course
if example is not None:
    history = example.history
    report_course = example.course
    render_example_banner()


def heading(text):
    """Section heading; sections that show example numbers say so."""
    return f"{tr('Example')} · {tr(text)}" if example is not None else tr(text)


sessions = [
    record["session"] for record in history.values()
]
attempts = [
    attempt
    for record in history.values()
    for attempt in record["attempts"]
]

# Include all course questions, plus those saved in graded sessions.
questions_by_id = {
    question.id: question for question in report_course.questions
}
for record in history.values():
    for question in record["questions"]:
        questions_by_id[question.id] = question

try:
    stats = calculate_topic_stats(
        attempts=attempts,
        sessions=sessions,
        questions=list(questions_by_id.values()),
    )
except ValueError:
    st.error(tr("Couldn't calculate your progress from this practice history."))
    st.stop()

mode_label = st.radio(
    tr("Performance mode"),
    options=[tr("Mock Exam"), tr("Topic Practice")],
    key=f"performance_mode_{course.course_id}",
    horizontal=True,
    width="stretch",
)
mode = "mock" if mode_label == tr("Mock Exam") else "topic"
mode_name = mode_label
st.caption(tr(f"Statistics for {mode_name}"))

mode_sessions = [
    session for session in sessions if session.mode == mode
]
mode_session_ids = {session.session_id for session in mode_sessions}
mode_attempts = [
    attempt for attempt in attempts
    if attempt.session_id in mode_session_ids
]
correct_count = sum(attempt.is_correct for attempt in mode_attempts)
overall_accuracy = (
    correct_count / len(mode_attempts) * 100 if mode_attempts else None
)

with st.container(key="progress_overview"):
    overview = st.columns(3)
    for column, label, value in (
        (overview[0], "Graded practice sessions", len(mode_sessions)),
        (overview[1], "Answers", len(mode_attempts)),
        (
            overview[2],
            "Accuracy",
            "—" if overall_accuracy is None else f"{overall_accuracy:.2f}%",
        ),
    ):
        with column.container(border=True):
            st.metric(tr(label), value)

if not history:
    st.info(
        tr("No graded practice sessions yet. Your topic list will update "
        "after you complete a practice session.")
    )

# Prefer persisted chronology when restoring histories; keep new local sessions last.
order = report_course.learning_state.get("session_order", [])
ordered_ids = [sid for sid in order if sid in history]
ordered_ids.extend(sid for sid in history if sid not in ordered_ids)

stats_by_topic = {
    item.topic_id: item
    for item in stats
    if item.mode == mode
}

# "View Learning DNA" on Home opens this page for that section, so it comes
# first on that visit (app.py forgets the request when the student moves on).
dna_first = st.session_state.get(f"progress_tab_{course.course_id}") == "Learning DNA"
first_block, second_block = st.container(), st.container()
charts_block, dna_block = (second_block, first_block) if dna_first else (first_block, second_block)

with charts_block:
    with st.container(border=True, key="progress_mastery"):
        st.subheader(heading("Mastery by topic"))
        render_bar_chart(
            heading("Mastery by topic"),
            mastery_rows(report_course.topics, stats_by_topic, tr),
            kind="mastery",
            empty_text="This course has no topics yet.",
        )
        help_tip(tr("Mastery uses each distinct question’s latest answer. Total accuracy still includes every graded attempt."))

    with st.container(border=True, key="progress_sessions"):
        st.subheader(heading("Accuracy by session"))
        render_session_chart(
            session_points(
                history[sid] for sid in ordered_ids if history[sid]["session"].mode == mode
            ),
            title=heading("Accuracy by session"),
            empty_text="No graded sessions in this mode yet.",
        )
        help_tip(tr("Each dot is one graded session, oldest on the left."))

with dna_block:
    render_learning_dna(
        report_course, attempts, [history[sid]["session"] for sid in ordered_ids],
        list(questions_by_id.values()), mode, example=example is not None,
    )
render_history_insights(report_course, history, mode, example=example is not None)

help_tip(
    tr("Insufficient evidence means fewer than 3 different questions for that topic "
    "in the selected mode. "
    "Below 60%: Weak · 60–79.99%: Developing · 80% or above: Mastered.")
)
if st.button(tr("Start practice"), type="primary"):
    from services.learning_flow import stage_practice
    stage_practice(st.session_state, course)
    st.switch_page("pages/2_Practice_Center.py")
