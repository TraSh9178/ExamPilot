"""Account forms shown before any learning pages are registered."""

from html import escape

import streamlit as st

from services.auth_service import login_user, register_user
from services.auth_session import start_authenticated_session
from services.i18n import LANGUAGE_KEY, tr
from services.ui_style import BRAND_LOGO, apply_app_styles, illustration_data_uri


def render_auth_page() -> None:
    apply_app_styles()
    # No sidebar exists before sign-in, so the full logo sits in the app header.
    st.logo(str(BRAND_LOGO), size="large")
    with st.container(key="auth_language"):
        st.toggle("中文界面 / Chinese interface", key=LANGUAGE_KEY)

    # One centred column: headline, campus watercolour, then the account card.
    with st.container(key="flight_auth_intro"):
        st.title(tr("Make your next study session count."))
        st.markdown(
            f'<img class="auth-campus" src="{illustration_data_uri("campus-watercolor")}" '
            f'alt="{escape(tr("Illustration of a university campus"))}">',
            unsafe_allow_html=True,
        )

    with st.container(border=True, key="auth_forms"):
        login_tab, register_tab = st.tabs([tr("Log in"), tr("Create account")])

        with login_tab:
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input(
                    tr("Username"), key="login_username", max_chars=32,
                    autocomplete="username",
                )
                password = st.text_input(
                    tr("Password"), type="password", key="login_password",
                    max_chars=128, autocomplete="current-password",
                )
                login_submitted = st.form_submit_button(
                    tr("Log in"), type="primary", use_container_width=True,
                )

            if login_submitted:
                if not username.strip() or not password:
                    st.error(tr("Enter your username and password."))
                else:
                    with st.spinner(tr("Logging in…")):
                        result = login_user(username, password)
                    if result.success and result.user is not None:
                        start_authenticated_session(st.session_state, result.user)
                        st.rerun()
                    else:
                        st.error(tr(result.message))

        with register_tab:
            with st.form("register_form", clear_on_submit=True):
                username = st.text_input(
                    tr("Username"), key="register_username", max_chars=32,
                    help=tr("3–32 characters: letters, numbers, periods, underscores, or hyphens. Usernames are case-insensitive."),
                    autocomplete="username",
                )
                password = st.text_input(
                    tr("Password"), type="password", key="register_password",
                    max_chars=128, autocomplete="new-password",
                )
                confirmation = st.text_input(
                    tr("Confirm password"), type="password",
                    key="register_password_confirm", max_chars=128,
                    autocomplete="new-password",
                )
                st.caption(tr("Use 15–128 characters. Try a memorable passphrase."))
                register_submitted = st.form_submit_button(
                    tr("Create account"), type="primary", use_container_width=True,
                )

            if register_submitted:
                if not username.strip() or not password:
                    st.error(tr("Enter a username and password."))
                elif password != confirmation:
                    st.error(tr("Passwords do not match."))
                else:
                    with st.spinner(tr("Creating your account…")):
                        result = register_user(username, password)
                    if result.success and result.user is not None:
                        start_authenticated_session(st.session_state, result.user)
                        st.rerun()
                    else:
                        st.error(tr(result.message))

        st.caption(tr("For your privacy, a browser refresh or an eight-hour session will require you to log in again."))
