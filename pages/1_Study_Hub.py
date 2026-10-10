import streamlit as st


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