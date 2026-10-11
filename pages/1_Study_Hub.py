import streamlit as st

from models.schemas import StudyPackage
from services.course_state import save_course
from services.gemini_service import generate_questions
from services.ui_style import apply_app_styles

apply_app_styles()

st.title("📚 Study Plan")
st.caption("Review course topics and choose the scope for your exam.")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard to start studying.")
    st.page_link("pages/0_Dashboard.py", label="Back to Dashboard")
    st.stop()

with st.container(key="study_plan_overview"):
    st.subheader(course.course_name)
    st.caption(f"{len(course.topics)} knowledge points")

if not course.topics:
    st.info("This course has no topics yet.")
else:
    for topic_number, topic in enumerate(course.topics, start=1):
        with st.container(border=True, key=f"study_topic_{topic.id}"):
            topic_columns = st.columns(
                [0.16, 4],
                vertical_alignment="top",
            )
            topic_columns[0].markdown(f"### {topic_number:02d}")
            topic_columns[1].markdown(f"### {topic.name}")
            st.write(topic.summary)

            if topic.source_pages:
                pages = ", ".join(
                    str(page) for page in topic.source_pages
                )
                st.caption(f"Source pages: {pages}")
            else:
                st.caption("Source pages not provided.")

# Keep scope confirmation separate for each course.
scope_key = f"scope_selection_{course.course_id}"
confirmed_key = f"confirmed_scope_{course.course_id}"
# Restore the selection when returning from another page.
if scope_key not in st.session_state:
    st.session_state[scope_key] = list(
        st.session_state.get(confirmed_key, [])
    )

with st.container(border=True, key="study_scope_panel"):
    st.subheader("Choose your exam scope")
    selected_topic_ids = st.multiselect(
        "Knowledge points",
        options=[topic.id for topic in course.topics],
        format_func=lambda topic_id: next(
            topic.name
            for topic in course.topics
            if topic.id == topic_id
        ),
        key=scope_key,
    )
    st.caption(
        f"Selected {len(selected_topic_ids)} / {len(course.topics)} "
        "knowledge points"
    )

    if st.button("Confirm exam scope", type="primary"):
        valid_topic_ids = {topic.id for topic in course.topics}

        if not selected_topic_ids:
            st.error("Select at least one topic.")
        elif len(selected_topic_ids) != len(set(selected_topic_ids)):
            st.error("Duplicate topic IDs are not allowed.")
        elif not set(selected_topic_ids).issubset(valid_topic_ids):
            st.error("The selection contains an invalid topic.")
        else:
            st.session_state[confirmed_key] = selected_topic_ids.copy()
            st.rerun()

# A changed selection requires confirmation again.
if st.session_state.get(confirmed_key) != selected_topic_ids:
    st.session_state.pop(confirmed_key, None)

confirmed_topic_ids = st.session_state.get(confirmed_key)

if confirmed_topic_ids:
    topic_count = len(confirmed_topic_ids)
    topic_label = "topic" if topic_count == 1 else "topics"

    st.success(f"Exam scope confirmed: {topic_count} {topic_label}.")

    document = st.session_state.get(
        f"course_document_{course.course_id}"
    )

    if document is not None:
        with st.container(border=True):
            st.subheader("Questions from your material")
            st.caption(
                "Generate candidate questions from this course material "
                "using only the confirmed topics. AI-generated questions "
                "may contain errors."
            )

            if st.button("Generate questions", type="primary"):
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
                        save_course(st.session_state, updated_course)
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
        if st.button("Start practice", type="primary"):
            st.switch_page("pages/2_Practice_Center.py")
    elif document is not None:
        st.info(
            "Generate questions for the confirmed scope "
            "before starting practice."
        )
    else:
        st.info("No questions are available in the confirmed scope.")
else:
    st.info("Confirm your topic selection before starting practice.")
