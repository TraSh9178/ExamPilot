import streamlit as st

from services.account_sync import (
    has_unresolved_conflicts,
    render_sidebar_status,
    restore_after_login,
)
from services.auth_session import current_user

from services.auth_ui import render_auth_page
from services.account_ui import render_account_page, render_account_sidebar
from services.ui_style import apply_app_styles
from services.tutor_assistant_ui import clear_tutor_browser_state, render_tutor_assistant

st.set_page_config(
    page_title="ExamPilot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

user = current_user(st.session_state)

if user is None:
    clear_tutor_browser_state()
    st.navigation(
        [st.Page(render_auth_page, title="Log in", icon=":material/login:", default=True)],
        position="hidden",
    ).run()
    st.stop()

restore_after_login(st.session_state)
apply_app_styles()
account_page = st.Page(
    render_account_page, title="My account", icon=":material/account_circle:",
    url_path="account", visibility="hidden",
)

pages = [
    st.Page(
        "pages/0_Dashboard.py",
        title="Dashboard",
        icon=":material/dashboard:",
        default=True,
    ),
    st.Page(
        "pages/1_Study_Hub.py",
        title="Study Plan",
        icon=":material/menu_book:",
    ),
    st.Page(
        "pages/2_Practice_Center.py",
        title="Practice",
        icon=":material/edit_note:",
    ),
    st.Page(
        "pages/3_Performance.py",
        title="Progress",
        icon=":material/monitoring:",
    ),
    st.Page(
        "pages/4_Knowledge_Graph.py",
        title="Knowledge Map",
        icon=":material/hub:",
    ),
    st.Page(
        "pages/5_Export_Anki.py",
        title="Export to Anki",
        icon=":material/download:",
    ),
]

navigation = st.navigation([*pages, account_page])
# Page widgets are cleaned up during navigation; rehydrate a course's saved
# scope once when entering its study page, not on every form interaction.
if st.session_state.get("_learning_page_path") != navigation.url_path:
    selected_course = st.session_state.get("current_course")
    if selected_course is not None:
        st.session_state.pop(f"scope_initialised_{selected_course.course_id}", None)
    st.session_state["_learning_page_path"] = navigation.url_path
render_account_sidebar(account_page)
with st.sidebar:
    render_sidebar_status()

# Reserve room for the floating entry at the bottom of narrow study pages.
st.markdown(
    """<style>
    @media (max-width: 480px) {
        [data-testid="stMain"] [data-testid="stMainBlockContainer"] {
            padding-bottom: 6rem;
        }
    }
    </style>""",
    unsafe_allow_html=True,
)
render_tutor_assistant()
navigation.run()
