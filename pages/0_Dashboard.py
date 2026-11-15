from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st

from models.schemas import StudyPackage
from services.account_sync import save_course_to_account
from services.course_state import (
    initialize_courses,
    remove_course,
    save_course,
    select_course,
)
from services.document_service import extract_document
from services.ai_service import generate_topics, generation_available
from services.course_icons import course_icon_svg
from services.demo_updates import demo_update
from services.guided_limits_ui import starter_question, start_demo
from services.learning_flow import stage_practice
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

st.title("Your study space")
st.caption("Choose a course or continue your next study session.")

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

with st.container(key="dashboard_actions"):
    if st.button(
        "Close setup" if st.session_state.show_course_setup else "Create course",
        icon=(":material/close:" if st.session_state.show_course_setup
              else ":material/add_circle_outline:"),
        key="create_course_button",
        type="secondary",
        use_container_width=True,
    ):
        st.session_state.show_course_setup = not st.session_state.show_course_setup
        st.rerun()

selected_course = st.session_state.get("current_course")
if selected_course is None:
    for course in st.session_state["courses"]:
        question = starter_question(course)
        if question is None:
            continue
        saved_scope = st.session_state.get(f"confirmed_scope_{course.course_id}")
        if not saved_scope or question.topic_id in saved_scope:
            with st.container(border=True, key="dashboard_demo_start"):
                st.caption("Calculus I demo · Limits")
                st.subheader("Try one question")
                st.write("Start with a short practice question. Use hints if you get stuck, then see what to work on next.")
                if st.button("Try a demo question", type="primary", key="try_limits_demo"):
                    start_demo(st.session_state, course, question)
                    st.switch_page("pages/2_Practice_Center.py")
        break
if selected_course is not None:
    with st.container(border=True, key="dashboard_continue"):
        st.caption("CONTINUE LEARNING")
        st.subheader(selected_course.course_name)
        active = st.session_state.get(f"active_practice_{selected_course.course_id}")
        confirmed = st.session_state.get(f"confirmed_scope_{selected_course.course_id}")
        main_action = "Continue practice" if active and "result" not in active else "Start practice" if confirmed else "Open Study Plan"
        if st.button(main_action, type="primary", key="dashboard_continue_learning", width="stretch"):
            if confirmed:
                if not active or "result" in active:
                    stage_practice(st.session_state, selected_course)
                else:
                    st.session_state.pop(f"practice_entry_{selected_course.course_id}", None)
                st.switch_page("pages/2_Practice_Center.py")
            else:
                st.switch_page("pages/1_Study_Hub.py")
        if active and "result" in active:
            if st.button("View latest result", key="dashboard_latest_result"):
                st.session_state.pop(f"practice_entry_{selected_course.course_id}", None)
                st.switch_page("pages/2_Practice_Center.py")

with st.container(key="dashboard_learning_dna"):
    if st.button(
        "View Learning DNA", icon=":material/insights:",
        key="learning_dna_open", disabled=selected_course is None,
    ):
        st.session_state[f"progress_tab_{selected_course.course_id}"] = "Learning DNA"
        st.switch_page("pages/3_Performance.py")

overview_details = st.expander("Study totals")
with overview_details:
    overview = st.container(key="dashboard_overview")

with st.container(key="dashboard_courses_header"):
    st.subheader("My courses")

if st.session_state.show_course_setup:
    with st.container(border=True, key="dashboard_course_setup"):
        st.subheader("Create a course")
        st.caption("1 · Name your course")
        st.text_input(
            "Course name",
            placeholder="e.g. Introduction to Biology",
            key="setup_course_name",
        )

        st.caption("2 · Upload materials and extract text")
        st.caption("When you save the course, extracted text and source pages are stored with your account. Original files are not stored.")
        uploaded_file = st.file_uploader(
            "Upload course materials",
            type=["pdf", "pptx", "txt", "png", "jpg", "jpeg"],
            accept_multiple_files=False,
            key="setup_course_file",
            max_upload_size=5,
        )

        st.caption(
            "PDF, PPTX, TXT, PNG or JPG/JPEG · up to 5 MiB per file · "
            "up to 50,000 characters of extracted text."
        )
        with st.expander("Supported materials"):
            st.caption(
                "Use UTF-8 TXT, text-based PDF or PPTX, or clear images of English text. "
                "Image text extraction requires Tesseract with English language support. "
                "Scanned PDF OCR, PPTX slide notes and DOCX are not supported."
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
            type="primary",
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

        st.caption("3 · Review the text and generate topics")
        if document is not None:
            st.success("Text extracted successfully.")

            extracted_text = document["text"]
            document_extension = Path(document["filename"]).suffix.lower()
            is_image_document = document_extension in {
                ".png", ".jpg", ".jpeg"
            }

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
                        else (
                            f"Image {page}"
                            if is_image_document
                            else f"Page {page}"
                        )
                    )
                )
                st.caption(f"{source['filename']} · {location}")

            if "pages" in document:
                page_label = (
                    "PPTX slides"
                    if document_extension == ".pptx"
                    else ("Image" if is_image_document else "PDF pages")
                )
                with st.expander(
                    f"{page_label} ({len(document['pages'])})"
                ):
                    for page in document["pages"]:
                        page_unit = (
                            "Slide"
                            if document_extension == ".pptx"
                            else ("Image" if is_image_document else "Page")
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

            if st.session_state.pop("course_generation_notice", False):
                st.success(
                    "Topics generated. Review them in Study Hub, "
                    "then confirm your exam scope."
                )

            st.caption(
                "Generating topics sends this material to Claude. "
                "You can review the topics before choosing your exam scope."
            )

            ai_available = generation_available()
            if st.button(
                "Generate topics",
                disabled=not course_name or not ai_available,
                type="primary",
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
                        sync_outcome = save_course_to_account(
                            st.session_state, new_course
                        )
                        if sync_outcome is not None and not sync_outcome.success:
                            st.warning(
                                "Course kept in this session but not saved to "
                                f"your account: {sync_outcome.message} "
                                "Use Save in Study Plan to retry."
                            )

                        st.success(
                            "Topics generated. Review them in Study Hub, "
                            "then confirm your exam scope."
                        )
                        st.session_state["course_generation_notice"] = True
                        st.rerun()


            if not ai_available:
                st.info(
                    "AI topic generation is not available on this server "
                    "because ANTHROPIC_API_KEY is not configured. The built-in "
                    "demo courses still work."
                )
            elif not course_name:
                st.info("Enter a course name to enable topic generation.")
        else:
            st.caption(
                "Extract your material to preview the text before generating topics."
            )

courses = st.session_state.courses
# Populate the overview after generation so it reflects a newly created course
# immediately, while keeping it above the setup panel on screen.
with overview:
    overview_columns = st.columns(3)
    with overview_columns[0]:
        st.metric("Courses", len(courses))
    with overview_columns[1]:
        st.metric(
            "Knowledge points",
            sum(len(course.topics) for course in courses),
        )
    with overview_columns[2]:
        st.metric(
            "Practice sessions",
            sum(
                len(
                    st.session_state.get(
                        f"practice_history_{course.course_id}", {}
                    )
                )
                for course in courses
            ),
        )

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
                with st.container(
                    border=True,
                    key=f"dashboard_course_card_{course.course_id}",
                ):
                    stage = st.session_state.get(
                        f"course_stage_{course.course_id}"
                    )
                    is_demo = any(
                        course.course_id == demo_id
                        for _, _, demo_id in DEMO_COURSES
                    )
                    st.caption(
                        "Generated course"
                        if stage
                        else ("Demo course" if is_demo else "Your course")
                    )
                    course_icon, course_details = st.columns([1, 3.5], vertical_alignment="center")
                    with course_icon:
                        st.markdown(
                            '<div class="academic-course-icon" aria-hidden="true">'
                            + course_icon_svg(course.course_id, course.course_name)
                            + '</div>',
                            unsafe_allow_html=True,
                        )
                    with course_details:
                        st.subheader(course.course_name)
                        st.caption(
                            f"{len(course.topics)} topics · "
                            f"{len(course.questions)} practice questions"
                        )
                    if is_demo:
                        updated_demo, added_count = demo_update(course)
                        if updated_demo != course:
                            added_topics = len(updated_demo.topics) - len(course.topics)
                            st.caption(f"Demo update available: {added_topics} new topics · {added_count} new questions. Existing answers and saved content are preserved. New questions need review in Study Plan; confirm new topics there before practice.")
                            update_label = "Add calculus knowledge update" if course.course_id == "calculus-i-demo" else "Add new demo questions"
                            if st.button(update_label, key=f"update_demo_{course.course_id}", width="stretch"):
                                save_course(st.session_state, updated_demo)
                                outcome = save_course_to_account(st.session_state, updated_demo)
                                if outcome is not None and not outcome.success:
                                    st.warning("Update kept in this session; account save failed. " + outcome.message)
                                else:
                                    st.rerun()
                    if stage == "topics_only":
                        st.caption("Next: review topics and choose your exam scope.")
                    action_columns = st.columns([1, 1])
                    with action_columns[0]:
                        if st.button(
                            "Open course",
                            type="primary",
                            key=f"open_course_{course.course_id}",
                            use_container_width=True,
                        ):
                            st.session_state.pop(
                                f"pending_course_removal_{course.course_id}", None
                            )
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
                            use_container_width=True,
                            help="Review a confirmation before deleting this course.",
                        ):
                            st.session_state[
                                f"pending_course_removal_{course.course_id}"
                            ] = True
                            st.rerun()

                    if st.session_state.get(
                        f"pending_course_removal_{course.course_id}", False
                    ):
                        st.warning(
                            f"Delete {course.course_name}? Its materials and practice "
                            "progress will be removed from this session."
                        )
                        confirmation_columns = st.columns(2)
                        with confirmation_columns[0]:
                            cancel_removal = st.button(
                                "Cancel",
                                key=f"cancel_remove_course_{course.course_id}",
                                type="secondary",
                                use_container_width=True,
                            )
                        with confirmation_columns[1]:
                            confirm_removal = st.button(
                                "Confirm delete",
                                key=f"confirm_remove_course_{course.course_id}",
                                type="secondary",
                                use_container_width=True,
                            )
                        if cancel_removal:
                            st.session_state.pop(
                                f"pending_course_removal_{course.course_id}", None
                            )
                            st.rerun()
                        if confirm_removal:
                            st.session_state.pop(
                                f"pending_course_removal_{course.course_id}", None
                            )
                            remove_course(
                                st.session_state,
                                course.course_id,
                            )
                            st.rerun()
