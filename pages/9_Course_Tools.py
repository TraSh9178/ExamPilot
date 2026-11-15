"""Course tools: question review, account backup and source material, one at a time."""
from services.ui_help import help_heading
from services.i18n import tr
import streamlit as st

from components.page_links import back_button
from services.account_sync import (
    SAVE_FAILED_MESSAGE,
    render_save_restore_controls,
    save_course_to_account,
)
from services.course_state import save_course
from services.question_editor import review_question, status_for
from services.ui_style import apply_app_styles

# The tools in display order: internal name -> label shown on the choice.
TOOLS = {
    "review": "Review and edit questions",
    "backup": "Account backup and recovery",
    "source": "Source material",
}
DEFAULT_TOOL = "review"


def render_question_review(course) -> None:
    """Pick a question, check or edit it, then approve or flag it."""
    editable = sorted([q for q in course.questions if status_for(course, q.id) != "superseded"], key=lambda q: status_for(course, q.id) != "pending")
    if editable:
        by_id = {q.id: q for q in editable}
        # Plain review labels; questions with no review decision get none.
        status_labels = {"pending": "Needs check", "approved": "Approved", "flagged": "Flagged"}

        def review_label(qid):
            text = by_id[qid].question[:100]
            status = status_labels.get(status_for(course, qid))
            return f"{tr(status)} · {text}" if status else text

        question_id = st.selectbox(
            tr("Question to review"), list(by_id),
            format_func=review_label,
            key=f"editor_question_{course.course_id}",
        )
        original = by_id[question_id]
        with st.form(f"question_review_{course.course_id}_{question_id}"):
            prompt = st.text_area(tr("Question text"), value=original.question)
            options = [st.text_input(tr(f"Option {chr(65 + index)}"), value=value) for index, value in enumerate(original.options)]
            correct = st.radio(tr("Correct answer"), list(range(4)), index=original.correct_index, format_func=lambda i: chr(65+i), horizontal=True)
            explanation = st.text_area(tr("Explanation"), value=original.explanation)
            with st.expander(tr("Question classification (advanced)")):
                # "untagged" stands in for None so every radio option is a real value.
                dimension_labels = {
                    "untagged": "Untagged", "computation": "Computation",
                    "conceptual": "Conceptual understanding",
                }
                dimensions = list(dimension_labels)
                dimension_choice = st.radio(
                    tr("Learning DNA evidence type"), dimensions,
                    index=dimensions.index(original.cognitive_dimension or "untagged"),
                    format_func=lambda value: tr(dimension_labels[value]),
                    horizontal=True,
                    help=tr("Choose what this question tests. Leave uncertain or mixed questions untagged; this label is not a student ability score."),
                )
                dimension = None if dimension_choice == "untagged" else dimension_choice
                structure = st.text_input(
                    tr("Practice structure label"), value=original.practice_structure or "", max_chars=80,
                    help=tr("A task type such as tangent_equation or derivative_at_point. Use the same label for the same task structure; leave uncertain questions blank."),
                )
            # The values stay English; only the shown words are translated.
            decision = st.radio(tr("Review decision"), ["Approve", "Flag as problematic"], format_func=tr, horizontal=True)
            apply_review = st.form_submit_button(tr("Save review"), type="primary")
        if apply_review:
            try:
                revised = review_question(course, question_id, "approved" if decision == "Approve" else "flagged",
                                          {"question": prompt, "options": options, "correct_index": correct, "explanation": explanation, "cognitive_dimension": dimension, "practice_structure": structure.strip() or None})
            except ValueError as error:
                st.error(tr(str(error)))
            else:
                save_course(st.session_state, revised)
                outcome = save_course_to_account(st.session_state, revised)
                if outcome is not None and not outcome.success:
                    st.warning(tr(SAVE_FAILED_MESSAGE))
                else:
                    st.session_state[f"question_review_notice_{course.course_id}"] = "Question review saved."
                    st.rerun()
    else:
        st.caption(tr("No questions available for review."))


def render_source_material(course) -> None:
    """The saved text of the course material, with a confirmed delete."""
    material = st.session_state.get(f"course_document_{course.course_id}")
    if material:
        st.caption(material.get("filename", tr("Course material")))
        with st.expander(tr("Read saved text")):
            st.text(material.get("text", ""))
        with st.form(f"material_delete_form_{course.course_id}"):
            confirm_delete = st.checkbox(tr("Delete this course's saved material"), key=f"confirm_material_delete_{course.course_id}")
            submitted_delete = st.form_submit_button(tr("Delete saved material"), key=f"delete_material_{course.course_id}")
        if submitted_delete and not confirm_delete:
            st.warning(tr("Select the confirmation checkbox before deleting material."))
        if submitted_delete and confirm_delete:
            metadata = dict(course.learning_state)
            metadata["document"] = None
            updated = course.model_copy(update={"learning_state": metadata})
            staged = dict(st.session_state)
            staged.pop(f"course_document_{course.course_id}", None)
            outcome = save_course_to_account(staged, updated)
            if outcome is not None and not outcome.success:
                st.error(tr("Couldn't delete the material from your account. Nothing was changed."))
            else:
                save_course(st.session_state, updated)
                st.session_state.pop(f"course_document_{course.course_id}", None)
                st.session_state[f"material_delete_notice_{course.course_id}"] = True
                st.rerun()
    else:
        st.caption(tr("No saved material for this course."))


apply_app_styles()

back_button(tr("Back to Study Plan"), "pages/1_Study_Hub.py", key="course_tools_back")
help_heading(tr("Course tools"), "\n\n".join([tr("Manage questions, account backups and source material when needed."), tr("Check the answer and explanation before approving; edits never change past results."), tr("The text from your material is saved with this course. The original uploaded file is not stored.")]), level='title')

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard to start studying."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

choice_key = f"course_tools_choice_{course.course_id}"
shown_key = f"course_tools_shown_{course.course_id}"
# The choice is cleared when another page runs, so the page always opens on
# the review tool. Clicking the chosen tool again would clear it; keep the
# tool that was on screen instead, so exactly one tool is always shown.
if st.session_state.get(choice_key) not in TOOLS:
    shown = st.session_state.get(shown_key) if choice_key in st.session_state else None
    st.session_state[choice_key] = shown if shown in TOOLS else DEFAULT_TOOL
tool = st.session_state[shown_key] = st.session_state[choice_key]
st.segmented_control(
    tr("Choose a tool"),
    options=list(TOOLS),
    format_func=lambda name: tr(TOOLS[name]),
    key=choice_key,
    label_visibility="collapsed",
)

if tool == "review":
    render_question_review(course)
elif tool == "backup":
    render_save_restore_controls(course)
else:
    render_source_material(course)

notice = st.session_state.pop(f"question_review_notice_{course.course_id}", None)
if notice:
    st.success(tr(notice))

if st.session_state.pop(f"material_delete_notice_{course.course_id}", False):
    st.success(tr("Saved material deleted."))
