from pathlib import Path

import streamlit as st

from models.schemas import StudyPackage


st.set_page_config(page_title="ExamPilot", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background-color: #F8FBFF;
        color: #102044;
    }

    [data-testid="stHeader"] {
        background-color: #F8FBFF;
    }

    h1, h2, h3, p {
        color: #102044;
    }

    [data-testid="stCaptionContainer"] p {
        color: #526581;
    }

    .stButton > button {
        background-color: #2166DB;
        color: white;
        border: 1px solid #2166DB;
        border-radius: 12px;
    }

    .stButton > button p {
        color: white;
    }

    .stButton > button:hover {
        background-color: #184FAE;
        color: white;
        border-color: #184FAE;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: white;
        border-color: #DCE6F4 !important;
        border-radius: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    card_column, _ = st.columns([1, 1])
    with card_column:
        with st.container(border=True):
            st.caption("Demo course")
            st.subheader(course.course_name)
            st.caption(
                f"{len(course.topics)} topics · "
                f"{len(course.questions)} practice questions"
            )
