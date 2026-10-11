import base64
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st

from models.schemas import StudyPackage
from services.course_state import (
    initialize_courses,
    remove_course,
    save_course,
    select_course,
)
from services.document_service import extract_document
from services.gemini_service import generate_topics
from services.ui_style import apply_app_styles

DEMO_COURSES = (
    ("Microeconomics Demo", "sample_course.json", "econ101"),
    ("Calculus I Demo", "calculus_i_demo.json", "calculus-i-demo"),
    ("Python Basics Demo", "demo_python_basics.json", "python-basics-demo"),
)


def load_demo_package(filename: str, expected_course_id: str) -> StudyPackage:
    demo_path = Path(__file__).resolve().parents[1] / "data" / filename
    course = StudyPackage.model_validate_json(
        demo_path.read_text(encoding="utf-8")
    )
    if course.course_id != expected_course_id:
        raise ValueError(
            f"Demo course ID mismatch in {filename}: "
            f"expected {expected_course_id}, got {course.course_id}"
        )
    return course


apply_app_styles()

campus_art = base64.b64encode(
    (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "campus-illustration.svg"
    ).read_bytes()
).decode("ascii")

st.markdown(
    f"""
    <section class="exam-hero" style="--campus-art: url('data:image/svg+xml;base64,{campus_art}')">
        <h1>Your next study session<br><span>starts here.</span></h1>
        <p>Turn course materials into focused exam practice.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

initialize_courses(st.session_state)

# Seed built-in examples once. The versioned marker adds Python Basics to
# sessions that already seeded the original two demos without restoring any
# demos the user previously removed.
if not st.session_state.get("default_demo_courses_v3_loaded", False):
    current_course = st.session_state["current_course"]
    loaded_course_ids = {
        course.course_id for course in st.session_state["courses"]
    }
    previous_demo_seeded = st.session_state.get(
        "default_demo_courses_loaded",
        False,
    )
    demo_courses_to_seed = (
        DEMO_COURSES[2:] if previous_demo_seeded else DEMO_COURSES
    )
    seed_succeeded = True
    for _, filename, expected_course_id in demo_courses_to_seed:
        if expected_course_id in loaded_course_ids:
            continue
        try:
            course = load_demo_package(filename, expected_course_id)
        except (OSError, ValueError) as error:
            seed_succeeded = False
            st.error(f"Could not load the default demo course: {error}")
        else:
            save_course(st.session_state, course)
            loaded_course_ids.add(course.course_id)
    st.session_state["current_course"] = current_course
    if seed_succeeded:
        st.session_state["default_demo_courses_loaded"] = True
        st.session_state["default_demo_courses_v3_loaded"] = True

# Keep the course setup panel open across page reruns.
if "show_course_setup" not in st.session_state:
    st.session_state.show_course_setup = False

if st.button(
    "Create course",
    icon=":material/add_circle_outline:",
    key="create_course_button",
    type="secondary",
):
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
            type=["pdf", "pptx", "txt", "png", "jpg", "jpeg"],
            accept_multiple_files=False,
            key="setup_course_file",
            max_upload_size=5,
        )

        st.caption(
            "Maximum file size: 5 MiB. "
            "Supports UTF-8 TXT, text-based PDF, text-based PPTX, and PNG/JPEG images (OCR via Tesseract + English language pack). "
            "Image OCR currently verified on macOS only; Windows support pending. "
            "PPTX slide notes, scanned PDF OCR, DOCX, and other formats are not supported."
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
            document_extension = Path(document["filename"]).suffix.lower()

            st.caption(
                f"Extracted text: {len(extracted_text):,} / 50,000 characters"
            )

            st.caption("Sources")
            for source in document["sources"]:
                page = source["page"]
                location = (
                    "TXT file (no page number)"
                    if page is None
                    else (
                        f"Slide {page}"
                        if document_extension == ".pptx"
                        else f"Page {page}"
                    )
                )
                st.caption(f"{source['filename']} · {location}")

            if "pages" in document:
                page_label = (
                    "PPTX slides"
                    if document_extension == ".pptx"
                    else "PDF pages"
                )
                with st.expander(
                    f"{page_label} ({len(document['pages'])})"
                ):
                    for page in document["pages"]:
                        page_unit = (
                            "Slide"
                            if document_extension == ".pptx"
                            else "Page"
                        )
                        st.markdown(
                            f"**{page_unit} {page['page']}** · "
                            f"{len(page['text']):,} characters"
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
courses = st.session_state.courses
st.subheader("📚 My courses")

if not courses:
    st.info("Create a course to get started.")
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
                    action_columns = st.columns([5, 1])
                    with action_columns[0]:
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
                    with action_columns[1]:
                        if st.button(
                            "Delete course",
                            icon=":material/delete:",
                            key=f"remove_course_{course.course_id}",
                            type="secondary",
                            help="Delete this course and its saved progress.",
                        ):
                            remove_course(
                                st.session_state,
                                course.course_id,
                            )
                            st.rerun()
