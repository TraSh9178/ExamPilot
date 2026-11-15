"""Export to Anki: the Flashcards download, on a page of its own."""
import streamlit as st

from components.page_links import back_button
from services.anki_export_ui import render_anki_export
from services.i18n import tr
from services.question_editor import available_questions
from services.ui_style import apply_app_styles

apply_app_styles()

back_button(tr("Back to Flashcards"), "pages/5_Export_Anki.py", key="anki_export_back")
st.title(tr("Export to Anki"))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.stop()

if not available_questions(course):
    st.info(tr("This course has no questions to export."))
    st.stop()

render_anki_export(course, st.session_state.get(f"practice_history_{course.course_id}", {}))
