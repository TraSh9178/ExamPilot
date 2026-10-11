import streamlit as st

from services.mastery_engine import (
    calculate_topic_stats,
    get_mastery_status,
)
from services.ui_style import apply_app_styles


apply_app_styles()

st.title("📈 Progress")
st.caption("Review practice results and see which topics need more evidence.")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("pages/0_Dashboard.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)

history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

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
    question.id: question for question in course.questions
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
except ValueError as error:
    st.error(f"Could not calculate performance: {error}")
    st.stop()

mode_label = st.radio(
    "Performance mode",
    options=["Mock Exam", "Topic Practice"],
    key=f"performance_mode_{course.course_id}",
    horizontal=True,
)
mode = "mock" if mode_label == "Mock Exam" else "topic"
mode_name = mode_label
st.caption(f"Statistics for {mode_name}")

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
            st.metric(label, value)

if not history:
    st.info(
        "No graded practice sessions yet. Your topic list will update "
        "after you complete a practice session."
    )

status_labels = {
    "unattempted": "Unattempted",
    "insufficient_evidence": "Insufficient evidence",
    "weak": "Weak",
    "developing": "Developing",
    "mastered": "Mastered",
}
status_colors = {
    "unattempted": "gray",
    "insufficient_evidence": "violet",
    "weak": "red",
    "developing": "orange",
    "mastered": "green",
}

stats_by_topic = {
    item.topic_id: item
    for item in stats
    if item.mode == mode
}

for topic in course.topics:
    topic_stats = stats_by_topic.get(topic.id)

    if topic_stats is None:
        attempted = 0
        correct = 0
        accuracy = None
        status = "unattempted"
    else:
        attempted = topic_stats.attempted
        correct = topic_stats.correct
        accuracy = topic_stats.accuracy
        status = get_mastery_status(topic_stats)

    with st.container(border=True, key=f"progress_topic_{topic.id}"):
        st.subheader(topic.name)
        topic_columns = st.columns([1, 1, 1.5])
        topic_columns[0].metric("Answers", attempted)
        topic_columns[1].metric(
            "Accuracy",
            "—" if accuracy is None else f"{accuracy:.2f}%",
        )
        with topic_columns[2]:
            st.caption("Mastery")
            st.badge(status_labels[status], color=status_colors[status])
        st.caption(
            (
                f"{correct} correct out of {attempted} answers."
                if attempted
                else "No answers recorded in this mode."
            )
        )

st.caption(
    "Insufficient evidence means fewer than 3 answers for that topic "
    "in the selected mode. "
    "Below 60%: Weak · 60–79.99%: Developing · 80% or above: Mastered."
)
st.caption(
    "Results are saved to your account when you are signed in and the save "
    "succeeds; otherwise they last only for this browser session."
)

if st.button("Start practice", type="primary"):
    st.switch_page("pages/2_Practice_Center.py")