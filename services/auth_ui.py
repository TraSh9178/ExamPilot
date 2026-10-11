"""Account forms shown before any learning pages are registered."""

import base64
from pathlib import Path

import streamlit as st

from services.auth_service import login_user, register_user
from services.auth_session import start_authenticated_session
from services.ui_style import apply_app_styles


def render_auth_page() -> None:
    apply_app_styles()
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] { max-width: 1120px; }
        [class*="st-key-auth_forms"] { margin-top: 1.5rem; }
        [data-testid="stFormSubmitButton"] > button {
            min-height: 3rem;
            border-radius: 0.75rem;
            font-weight: 650;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    intro, forms = st.columns([1.1, 1], gap="large")
    with intro:
        st.markdown("### 🎓 ExamPilot")
        st.title("Make your next study session count.")
        st.write("Turn your course materials into a focused study plan and exam practice.")
        art_path = Path(__file__).resolve().parents[1] / "assets" / "campus-illustration.svg"
        campus_art = base64.b64encode(art_path.read_bytes()).decode("ascii")
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{campus_art}" '
            'alt="Illustration of a university campus" '
            'style="width:100%;max-height:340px;object-fit:contain;margin-top:1rem;">',
            unsafe_allow_html=True,
        )

    with forms, st.container(border=True, key="auth_forms"):
        st.header("Welcome to ExamPilot")
        st.caption("Log in or create an account to start studying.")
        login_tab, register_tab = st.tabs(["Log in", "Create account"])

        with login_tab:
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input(
                    "Username", key="login_username", max_chars=32,
                    autocomplete="username",
                )
                password = st.text_input(
                    "Password", type="password", key="login_password",
                    max_chars=128, autocomplete="current-password",
                )
                login_submitted = st.form_submit_button(
                    "Log in", type="primary", use_container_width=True,
                )

            if login_submitted:
                if not username.strip() or not password:
                    st.error("Enter your username and password.")
                else:
                    with st.spinner("Logging in…"):
                        result = login_user(username, password)
                    if result.success and result.user is not None:
                        start_authenticated_session(st.session_state, result.user)
                        st.rerun()
                    else:
                        st.error(result.message)

        with register_tab:
            with st.form("register_form", clear_on_submit=True):
                username = st.text_input(
                    "Username", key="register_username", max_chars=32,
                    help="3–32 characters: letters, numbers, periods, underscores, or hyphens. Usernames are case-insensitive.",
                    autocomplete="username",
                )
                password = st.text_input(
                    "Password", type="password", key="register_password",
                    max_chars=128, autocomplete="new-password",
                )
                confirmation = st.text_input(
                    "Confirm password", type="password",
                    key="register_password_confirm", max_chars=128,
                    autocomplete="new-password",
                )
                st.caption("Use 15–128 characters. Try a memorable passphrase.")
                register_submitted = st.form_submit_button(
                    "Create account", type="primary", use_container_width=True,
                )

            if register_submitted:
                if not username.strip() or not password:
                    st.error("Enter a username and password.")
                elif password != confirmation:
                    st.error("Passwords do not match.")
                else:
                    with st.spinner("Creating your account…"):
                        result = register_user(username, password)
                    if result.success and result.user is not None:
                        start_authenticated_session(st.session_state, result.user)
                        st.rerun()
                    else:
                        st.error(result.message)

        st.caption("For your privacy, a browser refresh or an eight-hour session will require you to log in again.")
