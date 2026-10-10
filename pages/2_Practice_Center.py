import streamlit as st


st.set_page_config(
    page_title="Practice Center | ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Practice Center")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("app.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    st.warning("Confirm your exam scope in Study Hub first.")
    st.page_link("pages/1_Study_Hub.py", label="Go to Study Hub")
    st.stop()

# Validate the confirmed scope before offering practice settings.
topic_names = {topic.id: topic.name for topic in course.topics}

if (
    len(confirmed_topic_ids) != len(set(confirmed_topic_ids))
    or not set(confirmed_topic_ids).issubset(topic_names)
):
    st.error("The confirmed scope is invalid. Confirm it again in Study Hub.")
    st.page_link("pages/1_Study_Hub.py", label="Go to Study Hub")
    st.stop()

st.caption("Confirmed exam scope")

for confirmed_topic_id in confirmed_topic_ids:
    st.write(f"• {topic_names[confirmed_topic_id]}")

st.page_link(
    "pages/1_Study_Hub.py",
    label="Change exam scope",
)

mode_label = st.radio(
    "Practice mode",
    options=["Mock Exam", "Topic Practice"],
    key=f"practice_mode_{course.course_id}",
)

mode = "mock" if mode_label == "Mock Exam" else "topic"
topic_id = None

if mode == "topic":
    topic_id = st.selectbox(
        "Choose a confirmed topic",
        options=confirmed_topic_ids,
        format_func=lambda value: topic_names[value],
        key=f"practice_topic_{course.course_id}",
    )

requested_count = st.number_input(
    "Number of questions",
    min_value=1,
    max_value=50,
    value=10,
    step=1,
    key=f"practice_count_{course.course_id}",
)

st.info(
    "Practice setup preview only. Exam creation and grading "
    "are not connected yet."
)