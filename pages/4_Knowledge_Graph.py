import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from services.graph_service import build_graph
from services.graph_service import apply_mastery_to_nodes
from services.mastery_engine import (
    calculate_topic_stats,
    get_mastery_status,
)

st.set_page_config(
    page_title="Knowledge Graph | ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Knowledge Graph")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("app.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)
st.caption(f"{len(course.topics)} topics")

if not course.topics:
    st.info("This course has no topics yet.")
    st.stop()

mode_label = st.radio(
    "Mastery mode",
    options=["Mock Exam", "Topic Practice"],
    key=f"graph_mode_{course.course_id}",
    horizontal=True,
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
    status_by_topic = {
        item.topic_id: get_mastery_status(item)
        for item in stats
        if item.mode == mode
    }
except ValueError as error:
    st.error(f"Could not calculate mastery: {error}")
    st.stop()

graph = build_graph(course)
graph["nodes"] = apply_mastery_to_nodes(
    graph["nodes"],
    status_by_topic,
)

nodes = [
    Node(
        id=item["id"],
        label=item["label"].replace(" ", "\n", 1),
        title=item["status"].replace("_", " ").title(),
        shape="box",
        color={
            "background": "#FFFFFF",
            "border": item["color"],
            "highlight": {
                "background": "#EDF5FF",
                "border": "#2166DB",
            },
        },
        borderWidth=3,
        margin=18,
        font={
            "size": 17,
            "color": "#102044",
            "face": "Arial",
        },
    )
    for item in graph["nodes"]
]

edges = [
    Edge(
        source=item["source"],
        target=item["target"],
        title=item["type"],
        color="#8CA5C7",
        width=2,
        arrows="to" if item["type"] == "prerequisite" else "",
        smooth=False,
    )
    for item in graph["edges"]
]

config = Config(
    width="100%",
    height=360,
    directed=True,
    physics=False,
    hierarchical=True,
)

agraph(
    nodes=nodes,
    edges=edges,
    config=config,
)

st.caption(
    "Drag nodes to rearrange the graph. "
    "Arrows indicate prerequisite relationships."
)

if not edges:
    st.info("No relationships are provided for this course.")

st.caption(
    "Gray: Unattempted · Purple: Insufficient evidence · "
    "Red: Weak · Orange: Developing · Green: Mastered"
)