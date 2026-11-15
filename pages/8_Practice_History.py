"""Practice history: the course's unfinished and finished sessions, newest first."""
from services.i18n import tr
import streamlit as st

from components.page_links import back_button
from services.practice_pages_ui import (
    PRACTICE_PAGE, can_open_result, history_visit_key, open_saved_result, practice_label, resume_session,
)
from services.ui_style import apply_app_styles


def session_rows(records, *, unfinished):
    """One row per session: its label and one button. The click opens the practice page."""
    for sid in reversed(list(records)):
        with st.container(
            horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
            key=f"practice_history_row_{sid}",
        ):
            st.markdown(practice_label(records, sid, unfinished=unfinished))
            # A repeated click finds its session already open (or gone) and does nothing more.
            if unfinished:
                if st.button(tr("Resume"), icon=":material/play_arrow:", key=f"practice_history_resume_{sid}"):
                    if resume_session(st.session_state, course.course_id, sid):
                        st.switch_page(PRACTICE_PAGE)
            elif can_open_result(records[sid]):
                if st.button(tr("Open result"), icon=":material/fact_check:", key=f"practice_history_open_{sid}"):
                    if open_saved_result(st.session_state, course.course_id, sid):
                        st.switch_page(PRACTICE_PAGE)


apply_app_styles()

back_button(tr("Back to Practice"), PRACTICE_PAGE, key="practice_history_back")
st.title(tr("Practice history"))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard to start studying."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

# "Back to Practice" returns to the setup screen this page was opened from.
st.session_state[history_visit_key(course.course_id)] = True

drafts = st.session_state.get(f"practice_drafts_{course.course_id}", {})
history = st.session_state.get(f"practice_history_{course.course_id}", {})

if not drafts and not history:
    st.caption(tr("No practice sessions yet. Finished and unfinished sessions will appear here."))
    st.stop()

if drafts:
    st.subheader(tr("Unfinished sessions"))
    session_rows(drafts, unfinished=True)

if history:
    st.subheader(tr("Finished sessions"))
    session_rows(history, unfinished=False)
