import streamlit as st

from components.ai_assistant import render_ai_assistant

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
]

page = st.navigation(pages)
try:
    page.run()
finally:
    render_ai_assistant()
