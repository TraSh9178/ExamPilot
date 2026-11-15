from services.i18n import tr
import streamlit as st

from services.account_sync import (
    render_sidebar_status,
    restore_after_login,
)
from services.auth_session import current_user

from services.auth_ui import render_auth_page
from services.account_ui import render_account_page, render_account_controls
from services.accessibility import render_accessibility_controls
from services.ui_style import apply_app_styles
from services.tutor_assistant_ui import clear_tutor_browser_state, render_tutor_assistant

st.set_page_config(
    page_title="ExamPilot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
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
account_page = st.Page(
    render_account_page, title=tr("My account"), icon=":material/account_circle:",
    url_path="account", visibility="hidden",
)

pages = [
    st.Page(
        "pages/0_Dashboard.py",
        title=tr("Dashboard"),
        icon=":material/dashboard:",
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
    st.Page(
        "pages/6_Concept_Lab.py",
        title=tr("Concept Lab"),
        icon=":material/science:",
    ),
    st.Page(
        "pages/5_Export_Anki.py",
        title=tr("Export to Anki"),
        icon=":material/download:",
    ),
]

navigation = st.navigation([*pages, account_page], position="hidden")
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
            from services.practice_insights import settle_focus
            settle_focus(active, time.monotonic())
            active["focus_timer"]["since"] = None
    if selected_course is not None:
        st.session_state.pop(f"scope_initialised_{selected_course.course_id}", None)
    st.session_state["_learning_page_path"] = navigation.url_path
with st.container(key="flight_header"):
    brand, home, practice, review, analytics, account = st.columns(
        [1.65, 0.85, 0.95, 1.25, 1.05, 0.95], gap="small", vertical_alignment="center"
    )
    with brand:
        st.markdown(
            '<div class="flight-brand"><span aria-hidden="true">✈</span> ExamPilot</div>',
            unsafe_allow_html=True,
        )
    with home:
        st.page_link(pages[0], label=tr("Home"), icon=":material/home:", width="stretch")
    with practice:
        st.page_link(pages[2], label=tr("Practice"), icon=":material/edit_note:", width="stretch")
    with review:
        review_pages = {
            page.url_path: page
            for page in (pages[1], pages[4], pages[5], pages[6])
            if page.url_path != navigation.url_path
        }
        destination = st.selectbox(
            tr("Review & tools"), list(review_pages), index=None,
            format_func=lambda path: review_pages[path].title,
            placeholder=tr("Review & tools"), label_visibility="collapsed",
            key=f"flight_review_destination_{navigation.url_path}",
        )
        if destination is not None:
            st.switch_page(review_pages[destination])
    with analytics:
        st.page_link(pages[3], label=tr("Analytics"), icon=":material/monitoring:", width="stretch")
    with account, st.popover(tr("Account"), icon=":material/account_circle:", width="stretch"):
        render_account_controls(account_page)
        with st.expander(tr("Accessibility settings")):
            render_accessibility_controls()

if selected_course := st.session_state.get("current_course"):
    with st.container(key="flight_course_context"):
        st.caption(f"{selected_course.course_name}  /  {navigation.title}")

with st.container(key="flight_sync_status"):
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
