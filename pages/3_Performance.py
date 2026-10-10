import streamlit as st

from services.mastery_engine import (
    calculate_topic_stats,
    get_mastery_status,
)


st.set_page_config(
    page_title="Performance | ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Performance")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("app.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)

history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

if not history:
    st.info("Submit a practice session to see your performance.")
    st.page_link(
        "pages/2_Practice_Center.py",
        label="Go to Practice Center",
    )
    st.stop()

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

mode_sessions = [
    session for session in sessions if session.mode == mode
]
st.caption(f"Graded sessions: {len(mode_sessions)}")

status_labels = {
    "unattempted": "Unattempted",
    "insufficient_evidence": "Insufficient evidence",
    "weak": "Weak",
    "developing": "Developing",
    "mastered": "Mastered",
}

stats_by_topic = {
    item.topic_id: item
    for item in stats
    if item.mode == mode
}

rows = []
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

    rows.append(
        {
            "Topic": topic.name,
            "Attempted": attempted,
            "Correct": correct,
            "Accuracy": (
                "—" if accuracy is None else f"{accuracy:.2f}%"
            ),
            "Status": status_labels[status],
        }
    )

st.dataframe(
    rows,
    hide_index=True,
    use_container_width=True,
)

st.caption(
    "Mastery requires at least 3 attempts per topic in the selected mode. "
    "Below 60%: Weak · 60–79.99%: Developing · 80% or above: Mastered."
)
st.caption("Records are retained only in the current browser session.")

st.page_link(
    "pages/2_Practice_Center.py",
    label="Go to Practice Center",
)