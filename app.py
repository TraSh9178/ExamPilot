import streamlit as st

from services.account_sync import render_sidebar_status, restore_after_login
from services.auth_session import current_user, logout_session
from services.auth_ui import render_auth_page

st.set_page_config(
    page_title="ExamPilot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

user = current_user(st.session_state)

if user is None:
    st.navigation(
        [st.Page(render_auth_page, title="Log in", icon=":material/login:", default=True)],
        position="hidden",
    ).run()
    st.stop()

restore_after_login(st.session_state)

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
    render_sidebar_status()

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

st.navigation(pages).run()
