import streamlit as st

from services.auth_session import current_user, logout_session
from services.auth_ui import render_auth_page
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

with st.sidebar:
    st.caption("Signed in as")
    st.text(user.username)
    st.button(
        "Log out",
        key="logout_button",
        icon=":material/logout:",
        on_click=logout_session,
        args=(st.session_state,),
        use_container_width=True,
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

navigation = st.navigation(pages)

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
