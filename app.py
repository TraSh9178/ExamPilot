from pathlib import Path

from services.i18n import tr
import streamlit as st

from services.account_sync import (
    render_sidebar_status,
    restore_after_login,
)
from services.auth_session import current_user

from services.auth_ui import render_auth_page
from services.account_ui import render_account_menu, render_account_page
from services.accessibility import render_accessibility_controls
from services.ui_style import BRAND_LOGO, BRAND_PLANE, apply_app_styles
from services.tutor_assistant_ui import clear_tutor_browser_state, render_tutor_assistant

ROOT = Path(__file__).resolve().parent
# Another change adds this page; list it only once its file is present.
LEARNING_RADAR_PAGE = ROOT / "pages" / "7_Learning_Radar.py"

st.set_page_config(
    page_title="ExamPilot",
    page_icon="📚",
    layout="wide",
    # Streamlit opens the sidebar on wide screens and keeps it closed on phones.
    initial_sidebar_state="auto",
)

user = current_user(st.session_state)

if user is None:
    clear_tutor_browser_state()
    st.navigation(
        [st.Page(render_auth_page, title=tr("Log in"), icon=":material/login:", default=True)],
        position="hidden",
    ).run()
    st.stop()

restore_after_login(st.session_state)
# Built-in examples are a shared catalog, independent of account age or page.
from services.demo_updates import sync_demo_catalog
sync_demo_catalog(st.session_state)
apply_app_styles()
# The full logo heads the sidebar; the plane stays top-left when it is collapsed.
st.logo(str(BRAND_LOGO), icon_image=str(BRAND_PLANE), size="large")
account_page = st.Page(
    render_account_page, title=tr("My account"), icon=":material/account_circle:",
    url_path="account", visibility="hidden",
)

pages = [
    st.Page(
        "pages/0_Dashboard.py",
        title=tr("Home"),
        icon=":material/home:",
        default=True,
    ),
    st.Page(
        "pages/1_Study_Hub.py",
        title=tr("Study Plan"),
        icon=":material/menu_book:",
    ),
    st.Page(
        "pages/2_Practice_Center.py",
        title=tr("Practice"),
        icon=":material/edit_note:",
    ),
    st.Page(
        "pages/3_Performance.py",
        title=tr("Progress"),
        icon=":material/monitoring:",
    ),
    st.Page(
        "pages/4_Knowledge_Graph.py",
        title=tr("Knowledge Map"),
        icon=":material/hub:",
    ),
]
if LEARNING_RADAR_PAGE.exists():
    pages.append(
        st.Page(
            "pages/7_Learning_Radar.py",
            title=tr("Learning Radar"),
            icon=":material/radar:",
        )
    )
pages += [
    st.Page(
        "pages/6_Concept_Lab.py",
        title=tr("Concept Lab"),
        icon=":material/science:",
    ),
    st.Page(
        "pages/5_Export_Anki.py",
        title=tr("Flashcards"),
        icon=":material/style:",
        url_path="Flashcards",
    ),
]

# Default position: the page list lives in Streamlit's collapsible sidebar.
navigation = st.navigation([*pages, account_page])
# Page widgets are cleaned up during navigation; rehydrate a course's saved
# scope once when entering its study page, not on every form interaction.
if st.session_state.get("_learning_page_path") != navigation.url_path:
    selected_course = st.session_state.get("current_course")
    if selected_course is not None:
        if navigation.url_path == "Practice_Center":
            st.session_state[f"rehydrate_practice_{selected_course.course_id}"] = True
        active = st.session_state.get(f"active_practice_{selected_course.course_id}")
        if active and "result" not in active and active.get("focus_timer"):
            import time
            from services.practice_insights import pause_or_resume_for_page
            # Time on other pages is not counted; the clock starts again on return.
            pause_or_resume_for_page(
                active, navigation.url_path == "Practice_Center", time.monotonic(),
            )
    if selected_course is not None:
        st.session_state.pop(f"scope_initialised_{selected_course.course_id}", None)
    st.session_state["_learning_page_path"] = navigation.url_path

# Save status follows the page list; accessibility settings stay at the very
# bottom of the sidebar, below the watercolour.
with st.sidebar:
    with st.container(key="sidebar_footer"):
        with st.container(key="flight_sync_status"):
            render_sidebar_status()
    with st.container(key="sidebar_accessibility"):
        with st.expander(tr("Accessibility settings")):
            render_accessibility_controls()

# Account: a round avatar in the top-right corner of every page.
render_account_menu(account_page)

if selected_course := st.session_state.get("current_course"):
    with st.container(key="flight_course_context"):
        st.caption(f"{selected_course.course_name}  /  {navigation.title}")

render_tutor_assistant()
navigation.run()
