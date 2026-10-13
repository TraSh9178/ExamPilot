import csv
import re
from io import StringIO

import streamlit as st

from services.anki_export_service import (
    export_anki_tsv,
    get_weak_topic_ids,
)
from services.mastery_engine import calculate_topic_stats
from services.ui_style import apply_app_styles


def _safe_filename(course_name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", course_name.strip())
    token = token.strip("_-").lower()[:80]
    return f"anki_{token or 'course'}.tsv"


def _topic_tag(topic_id: str) -> str:
    return "topic_" + re.sub(r"\s+", "_", topic_id.strip())


apply_app_styles()

st.title("Export to Anki")
st.caption(
    "Review course knowledge cards here or download a UTF-8 TSV file "
    "for Anki text import. "
    "AnkiWeb sync is not supported; Anki Desktop import has not been verified."
)

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.stop()

with st.container(key="anki_course_heading"):
    st.subheader(course.course_name)

if not course.questions:
    st.info("This course has no questions to export.")
    st.stop()

export_scope = st.radio(
    "Questions to export",
    options=["All Questions", "Weak Topics"],
    key=f"anki_export_scope_{course.course_id}",
    horizontal=True,
    width="stretch",
)

topic_ids = None

if export_scope == "Weak Topics":
    mode_label = st.radio(
        "Practice mode",
        options=["Mock Exam", "Topic Practice"],
        key=f"anki_export_mode_{course.course_id}",
        horizontal=True,
    width="stretch",
    )
    mode = "mock" if mode_label == "Mock Exam" else "topic"

    history_key = f"practice_history_{course.course_id}"
    history = st.session_state.get(history_key, {})
    sessions = [record["session"] for record in history.values()]
    attempts = [
        attempt
        for record in history.values()
        for attempt in record["attempts"]
    ]

    questions_by_id = {question.id: question for question in course.questions}
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
        st.error(f"Could not calculate mastery: {error}")
        st.stop()

    topic_ids = get_weak_topic_ids(stats, mode)
    if not topic_ids:
        st.info("No weak or developing topics in this practice mode.")
        st.stop()

    if not any(question.topic_id in topic_ids for question in course.questions):
        st.info("No questions match the weak or developing topics.")
        st.stop()

content = export_anki_tsv(course, topic_ids=topic_ids)
if not content:
    st.info("No questions match the selected export.")
    st.stop()

cards = list(csv.reader(StringIO(content), delimiter="\t"))
st.caption(f"{len(cards)} study cards shown and ready to export.")
topic_names_by_tag = {
    _topic_tag(topic.id): topic.name
    for topic in course.topics
}

with st.container(border=True, key="anki_export_summary"):
    summary_column, download_column = st.columns([1.4, 1], vertical_alignment="center")
    with summary_column:
        st.markdown("**Your review deck**")
        st.caption(f"{len(cards)} cards · {export_scope} · UTF-8 TSV")
    with download_column:
        st.download_button(
            "Download Anki TSV",
            data=content.encode("utf-8"),
            file_name=_safe_filename(course.course_name),
            mime="text/tab-separated-values; charset=utf-8",
            type="primary",
            use_container_width=True,
        )

st.subheader("Study cards")
st.caption("Try each question, then reveal its answer and explanation.")
for index, (front, back, tags) in enumerate(cards, start=1):
    question, _, options = front.partition("\n")
    answer, _, explanation = back.partition("\n")
    topic_name = next(
        (
            topic_names_by_tag[tag]
            for tag in tags.split()
            if tag in topic_names_by_tag
        ),
        "Course review",
    )

    with st.container(border=True, key=f"anki_study_card_{index}"):
        st.caption(f"{index:02d} / {len(cards)} · {topic_name}")
        st.markdown(f"#### {question}")
        st.text(options, width="stretch")
        with st.expander("Show answer and explanation"):
            st.success(answer.removeprefix("Correct answer: "))
            st.write(explanation.removeprefix("Explanation: "))
