import streamlit as st

from services.tutor_assistant_ui import render_tutor_assistant

st.set_page_config(
    page_title="ExamPilot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
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

with st.sidebar:
    st.divider()
    st.caption("CURRENT COURSE")
    current_course = st.session_state.get("current_course")
    if current_course is None:
        st.caption("Open a course from the Dashboard to get started.")
    else:
        st.text(current_course.course_name)
        st.page_link(
            "pages/0_Dashboard.py",
            label="Switch course",
            icon=":material/swap_horiz:",
        )

render_tutor_assistant()
navigation.run()
