import streamlit as st

from models.schemas import StudyPackage
from services.gemini_service import generate_questions

st.set_page_config(
    page_title="Study Hub | ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Study Hub")

# Read the course selected on the dashboard.
course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard to start studying.")
    st.page_link("app.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)
st.caption(f"{len(course.topics)} topics")

if not course.topics:
    st.info("This course has no topics yet.")
else:
    for topic in course.topics:
        with st.container(border=True):
            st.subheader(topic.name)
            st.write(topic.summary)

            if topic.source_pages:
                pages = ", ".join(
                    str(page) for page in topic.source_pages
                )
                st.caption(f"Source pages: {pages}")
            else:
                st.caption("Source pages not provided.")

st.divider()
st.subheader("Confirm exam scope")

# Keep scope confirmation separate for each course.
scope_key = f"scope_selection_{course.course_id}"
confirmed_key = f"confirmed_scope_{course.course_id}"

selected_topic_ids = st.multiselect(
    "Choose topics for your exam",
    options=[topic.id for topic in course.topics],
    format_func=lambda topic_id: next(
        topic.name
        for topic in course.topics
        if topic.id == topic_id
    ),
    default=[],
    key=scope_key,
)

# A changed selection requires confirmation again.
if st.session_state.get(confirmed_key) != selected_topic_ids:
    st.session_state.pop(confirmed_key, None)

if st.button("Confirm exam scope"):
    valid_topic_ids = {topic.id for topic in course.topics}

    if not selected_topic_ids:
        st.error("Select at least one topic.")
    elif len(selected_topic_ids) != len(set(selected_topic_ids)):
        st.error("Duplicate topic IDs are not allowed.")
    elif not set(selected_topic_ids).issubset(valid_topic_ids):
        st.error("The selection contains an invalid topic.")
    else:
        st.session_state[confirmed_key] = selected_topic_ids.copy()

confirmed_topic_ids = st.session_state.get(confirmed_key)

if confirmed_topic_ids:
    topic_count = len(confirmed_topic_ids)
    topic_label = "topic" if topic_count == 1 else "topics"

    st.success(
        f"Exam scope confirmed: {topic_count} {topic_label}."
    )

    document = st.session_state.get(
        f"course_document_{course.course_id}"
    )

    if document is not None:
        st.caption(
            "Generate candidate questions from your material "
            "using only the confirmed topics. "
            "AI-generated questions may contain errors."
        )

        if st.button("Generate questions"):
            with st.spinner("Generating questions..."):
                generated = generate_questions(
                    document,
                    course,
                    list(confirmed_topic_ids),
                )

            if not generated["ok"]:
                st.error(generated["message"])
            else:
                try:
                    updated_course = StudyPackage.model_validate(
                        generated["package"]
                    )
                except ValueError as error:
                    st.error(
                        f"Could not load generated questions: {error}"
                    )
                else:
                    st.session_state.current_course = updated_course
                    st.session_state[
                        f"course_stage_{course.course_id}"
                    ] = "questions_generated"

                    # Previous practice used the old question set.
                    st.session_state.pop(
                        f"active_practice_{course.course_id}",
                        None,
                    )
                    st.rerun()

    available_count = sum(
        question.topic_id in confirmed_topic_ids
        for question in course.questions
    )

    st.caption(
        f"Available questions in confirmed scope: {available_count}"
    )

    if available_count:
        st.page_link(
            "pages/2_Practice_Center.py",
            label="Go to Practice Center",
        )
    elif document is not None:
        st.info(
            "Generate questions for the confirmed scope "
            "before starting practice."
        )
    else:
        st.info("No questions are available in the confirmed scope.")
else:
    st.info("Confirm your topic selection before starting an exam.")