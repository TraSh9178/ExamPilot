import streamlit as st
from components.knowledge_graph import (
    render_knowledge_graph,
    get_selected_topic_details,
    render_topic_details,
)
from services.graph_service import build_mastery_graph
from services.mastery_engine import calculate_topic_stats
from services.ui_style import apply_app_styles

apply_app_styles()

st.title("Knowledge Map")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("pages/0_Dashboard.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)
st.caption(f"{len(course.topics)} knowledge points")

if not course.topics:
    st.info("This course has no topics yet.")
    st.stop()

with st.container(border=True):
    st.caption("Mastery mode")
    mode_label = st.radio(
        "Mastery mode",
        options=["Mock Exam", "Topic Practice"],
        key=f"graph_mode_{course.course_id}",
        horizontal=True,
        label_visibility="collapsed",
    )
mode = "mock" if mode_label == "Mock Exam" else "topic"

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
    st.error(f"Could not calculate mastery: {error}")
    st.stop()

graph_column, details_column = st.columns([2.2, 1])

with graph_column:
    with st.container(border=True):
        selected_node_id = render_knowledge_graph(course, stats, mode)

        st.markdown(
            """
            <div class="graph-legend">
                <span><i style="background:#94A3B8"></i>Unattempted</span>
                <span><i style="background:#A78BFA"></i>Insufficient evidence</span>
                <span><i style="background:#EF4444"></i>Weak</span>
                <span><i style="background:#F59E0B"></i>Developing</span>
                <span><i style="background:#22C55E"></i>Mastered</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Click to view details · Drag to move · Scroll to zoom")

    if not course.relationships:
        st.info("No topic relationships are available for this course.")

with details_column:
    with st.container(border=True):
        details = None
        if selected_node_id is not None:
            graph = build_mastery_graph(course, stats, mode)
            details = get_selected_topic_details(
                selected_node_id, course, graph
            )
        render_topic_details(details)