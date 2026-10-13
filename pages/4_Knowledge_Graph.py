from pathlib import Path

import streamlit as st
from components.knowledge_graph import (
    render_knowledge_graph,
    get_selected_topic_details,
    render_topic_details,
)
from services.graph_exploration import local_graph, related_topics
from services.graph_service import build_mastery_graph
from services.mastery_engine import calculate_topic_stats
from services.course_state import save_course
from services.ui_style import apply_app_styles

apply_app_styles()

st.title("Knowledge Map")
st.caption("Explore connected ideas. Click a topic to read its summary and learning progress.")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("pages/0_Dashboard.py", label="Back to Dashboard")
    st.stop()

if course.course_id == "calculus-i-demo" and not course.relationships:
    demo_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "calculus_i_demo.json"
    )
    try:
        demo_course = type(course).model_validate_json(
            demo_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        st.error(f"Could not update the Calculus demo course: {error}")
        st.stop()

    if demo_course.relationships:
        course = course.model_copy(
            update={"relationships": demo_course.relationships}
        )
        save_course(st.session_state, course)

with st.container(key="graph_course_heading"):
    st.subheader(course.course_name)
    st.caption(f"{len(course.topics)} knowledge points")

if not course.topics:
    st.info("This course has no topics yet.")
    st.stop()

mode_column, search_column, local_column = st.columns([1.4, 1.8, .8], vertical_alignment="bottom")
mode_label = mode_column.radio(
    "Progress mode", options=["Mock Exam", "Topic Practice"],
    key=f"graph_mode_{course.course_id}", horizontal=True,
)
mode = "mock" if mode_label == "Mock Exam" else "topic"

topic_names = {topic.id: topic.name for topic in course.topics}
pending_key = f"graph_pending_focus_{course.course_id}"
if pending_key in st.session_state:
    st.session_state[f"graph_focus_{course.course_id}"] = st.session_state.pop(pending_key)
focus_id = search_column.selectbox(
    "Find a topic", options=[None, *topic_names],
    format_func=lambda value: "All topics" if value is None else topic_names[value],
    key=f"graph_focus_{course.course_id}",
)
local_view = local_column.toggle(
    "Local graph", disabled=focus_id is None,
    key=f"graph_local_{course.course_id}",
    help="Show only this topic and its directly connected neighbors.",
)
view_course = local_graph(course, focus_id) if focus_id and local_view else course
st.caption(f"Showing {len(view_course.topics)} of {len(course.topics)} topics · Connections: {len(view_course.relationships)}")

reset_key = f"graph_view_reset_{course.course_id}_{mode}"
zoom_key = f"graph_zoom_{course.course_id}_{mode}"
zoom_level = st.session_state.get(zoom_key, 0)
graph_controls = st.columns([1.4, 3])
with graph_controls[0]:
    if st.button(
        "Fit to view / Reset view",
        key=f"reset_graph_view_{course.course_id}_{mode}",
        icon=":material/fit_screen:",
    ):
        st.session_state[reset_key] = (
            st.session_state.get(reset_key, 0) + 1
        )
        st.session_state[zoom_key] = 0
        st.rerun()
with graph_controls[1]:
    st.caption("Click for details · Drag to rearrange · Scroll to zoom")

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

graph_column, details_column = st.columns([2.5, 1], gap="medium")

with graph_column:
    with st.container(border=True, key="knowledge_graph_canvas"):
        zoom_controls = st.columns([1, 0.08, 0.08])
        with zoom_controls[1]:
            if st.button(
                "−",
                key=f"graph_zoom_out_{course.course_id}_{mode}",
                help="Make nodes smaller",
                disabled=zoom_level <= -3,
            ):
                st.session_state[zoom_key] = zoom_level - 1
        with zoom_controls[2]:
            if st.button(
                "+",
                key=f"graph_zoom_in_{course.course_id}_{mode}",
                help="Make nodes larger",
                disabled=zoom_level >= 3,
            ):
                st.session_state[zoom_key] = zoom_level + 1

        zoom_level = st.session_state.get(zoom_key, 0)
        zoom_scale = 1 + zoom_level * 0.15
        selected_node_id = render_knowledge_graph(
            view_course,
            stats,
            mode,
            view_reset=st.session_state.get(reset_key, 0),
            node_scale=zoom_scale,
            focus_topic_id=focus_id,
        )


    if not course.relationships:
        st.info("This course has no topic relationships yet.")

# Synchronize canvas clicks with the keyboard-accessible topic picker.
last_click_key = f"graph_last_click_{course.course_id}_{mode}"
if selected_node_id != st.session_state.get(last_click_key):
    st.session_state[last_click_key] = selected_node_id
    if selected_node_id is None or selected_node_id in topic_names:
        st.session_state[pending_key] = selected_node_id
        st.rerun()
selected_node_id = focus_id

with details_column:
    with st.container(border=True, key="knowledge_graph_details"):
        details = None
        topic_stats = None
        if selected_node_id is not None:
            graph = build_mastery_graph(course, stats, mode)
            details = get_selected_topic_details(
                selected_node_id, course, graph
            )
            topic_stats = next(
                (
                    item
                    for item in stats
                    if item.topic_id == selected_node_id
                    and item.mode == mode
                ),
                None,
            )
        render_topic_details(details, topic_stats)
        if details is not None:
            links = related_topics(course, selected_node_id)
            st.divider()
            st.markdown("**Connected topics**")
            for label, group in (("Prerequisites", "prerequisites"), ("Leads to", "next_topics"), ("Related", "related")):
                if links[group]:
                    st.caption(label + ": " + ", ".join(topic_names[item] for item in links[group]))
            if not any(links.values()):
                st.caption("No connections recorded for this topic.")
            st.caption("These are course-provided relationships, not a diagnosis of your understanding.")

    with st.container(border=True, key="knowledge_graph_legend"):
        st.markdown("**Status Legend**")
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
