from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st

from models.schemas import StudyPackage
from services.course_state import initialize_courses, save_course, select_course
from services.document_service import extract_document
from services.gemini_service import generate_topics

st.set_page_config(
    page_title="ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    [data-testid="stTextInput"] input {
    background-color: white;
    color: #102044;
    border: 1px solid #DCE6F4;
    }

    [data-testid="stTextInput"] input::placeholder {
        color: #526581;
    }

    [data-testid="stFileUploaderDropzone"] {
        background-color: #EDF5FF;
        border: 1px dashed #8CB4ED;
    }

    [data-testid="stFileUploaderDropzone"] button {
        background-color: #2166DB !important;
        border: 1px solid #2166DB !important;
        color: white !important;
    }

    [data-testid="stFileUploaderDropzone"] button p {
        color: white !important;
    }
    
    [data-testid="stExpandSidebarButton"] button {
        background-color: #2166DB !important;
        color: white !important;
        border: 1px solid #2166DB !important;
    }

    [data-testid="stExpandSidebarButton"] button svg {
        fill: currentColor !important;
        color: white !important;
    }
    .stButton > button:disabled {
        background-color: #E2E8F0 !important;
        border-color: #CBD5E1 !important;
        color: #475569 !important;
        opacity: 1 !important;
    }

    .stButton > button:disabled p {
        color: #475569 !important;
    }
    .stButton > button:not(:disabled),
    .stButton > button:not(:disabled):hover,
    .stButton > button:not(:disabled):focus,
    .stButton > button:not(:disabled):focus-visible,
    .stButton > button:not(:disabled):active {
        background-color: #2166DB !important;
        border-color: #2166DB !important;
        color: #FFFFFF !important;
    }

    .stButton > button:not(:disabled) p {
        color: #FFFFFF !important;
    }

    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        color: #526581 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("ExamPilot")
st.write("Turn course materials into focused exam practice.")

initialize_courses(st.session_state)

# Keep the course setup panel open across page reruns.
if "show_course_setup" not in st.session_state:
    st.session_state.show_course_setup = False

demo_courses = (
    (
        "Load Introduction to Microeconomics Demo",
        "sample_course.json",
        "load_demo_econ101",
    ),
    (
        "Load Calculus I Demo",
        "calculus_i_demo.json",
        "load_demo_calculus_i",
    ),
)
demo_columns = st.columns(3)

for column, (button_label, filename, button_key) in zip(
    demo_columns,
    demo_courses,
):
    with column:
        if st.button(
            button_label,
            use_container_width=True,
            key=button_key,
        ):
            demo_path = (
                Path(__file__).resolve().parent / "data" / filename
            )

            try:
                course = StudyPackage.model_validate_json(
                    demo_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as error:
                st.error(f"Could not load the demo course: {error}")
            else:
                save_course(st.session_state, course)

with demo_columns[2]:
    if st.button("Create course", use_container_width=True):
        st.session_state.show_course_setup = True

if st.session_state.show_course_setup:
    with st.container(border=True):
        st.subheader("Create a course")

        if st.button("Close setup"):
            st.session_state.show_course_setup = False
            st.rerun()

        st.text_input(
            "Course name",
            placeholder="e.g. Introduction to Biology",
            key="setup_course_name",
        )

        uploaded_file = st.file_uploader(
            "Upload course materials",
            type=["pdf", "txt"],
            accept_multiple_files=False,
            key="setup_course_file",
        )

        st.caption(
            "Maximum file size: 5 MiB. "
            "Supports UTF-8 TXT and text-based PDF. "
            "Scanned PDFs are not supported."
        )

        file_bytes = (
            uploaded_file.getvalue()
            if uploaded_file is not None
            else None
        )
        source_key = (
            (uploaded_file.name, sha256(file_bytes).hexdigest())
            if uploaded_file is not None
            else None
        )

        # Clear extracted content when the uploaded file changes.
        if st.session_state.get("setup_document_source") != source_key:
            st.session_state.pop("setup_document", None)
            st.session_state["setup_document_source"] = source_key

        if st.button(
            "Extract text",
            disabled=uploaded_file is None,
        ):
            with st.spinner("Extracting text..."):
                document = extract_document(
                    file_bytes,
                    uploaded_file.name,
                )

            if not document["ok"]:
                st.session_state.pop("setup_document", None)
                st.error(document["message"])
            else:
                st.session_state["setup_document"] = document

        document = st.session_state.get("setup_document")

        if document is not None:
            st.success("Text extracted successfully.")

            extracted_text = document["text"]

            st.caption(
                f"Extracted text: {len(extracted_text):,} characters"
            )

            with st.expander("Preview extracted text"):
                st.text(extracted_text)

            course_name = st.session_state.get(
                "setup_course_name", ""
            ).strip()

            st.caption(
                "Generate topics sends the extracted material to Gemini. "
                "Review the generated topics before confirming exam scope."
            )

            if st.button(
                "Generate topics",
                disabled=not course_name,
            ):
                course_id = str(uuid4())

                with st.spinner("Generating topics..."):
                    generated = generate_topics(
                        document=document,
                        course_id=course_id,
                        course_name=course_name,
                    )

                if not generated["ok"]:
                    st.error(generated["message"])
                else:
                    try:
                        new_course = StudyPackage.model_validate(
                            generated["package"]
                        )
                    except ValueError as error:
                        st.error(
                            f"Could not load generated topics: {error}"
                        )
                    else:
                        # Retain the material for later question generation.
                        st.session_state[
                            f"course_document_{new_course.course_id}"
                        ] = document
                        st.session_state[
                            f"course_stage_{new_course.course_id}"
                        ] = "topics_only"
                        save_course(st.session_state, new_course)

                        st.success(
                            "Topics generated. Review them in Study Hub, "
                            "then confirm your exam scope."
                        )

            if not course_name:
                st.info("Enter a course name to enable topic generation.")
st.subheader("My courses")

courses = st.session_state.courses

if not courses:
    st.info("Load the demo course to get started.")
else:
    for row_start in range(0, len(courses), 2):
        card_columns = st.columns(2)

        for column, course in zip(
            card_columns,
            courses[row_start : row_start + 2],
        ):
            with column:
                with st.container(border=True):
                    stage = st.session_state.get(
                        f"course_stage_{course.course_id}"
                    )
                    st.caption(
                        "Generated course" if stage else "Demo course"
                    )
                    st.subheader(course.course_name)
                    st.caption(
                        f"{len(course.topics)} knowledge points · "
                        f"{len(course.questions)} practice questions"
                    )
                    if st.button(
                        "Open course",
                        type="primary",
                        key=f"open_course_{course.course_id}",
                        use_container_width=True,
                    ):
                        select_course(
                            st.session_state,
                            course.course_id,
                        )
                        st.switch_page("pages/1_Study_Hub.py")
