from pathlib import Path

import streamlit as st

from models.schemas import StudyPackage


st.set_page_config(page_title="ExamPilot", layout="wide")

st.title("ExamPilot")
st.write("Turn course materials into focused exam practice.")

if "current_course" not in st.session_state:
    st.session_state.current_course = None

if st.button("Load demo course"):
    sample_path = (
        Path(__file__).resolve().parent / "data" / "sample_course.json"
    )

    try:
        course = StudyPackage.model_validate_json(
            sample_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        st.error(f"Could not load the demo course: {error}")
    else:
        st.session_state.current_course = course

st.subheader("My courses")

course = st.session_state.current_course

if course is None:
    st.info("Load the demo course to get started.")
else:
    st.write(course.course_name)
    st.caption(
        f"{len(course.topics)} topics · "
        f"{len(course.questions)} practice questions"
    )