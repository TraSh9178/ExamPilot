"""Account identity and session avatar controls behind the existing Auth gate."""

import base64
from html import escape

import streamlit as st

from services.account_profile import (
    get_account_avatar,
    remove_account_avatar,
    save_account_avatar,
)
from services.auth_session import current_user, logout_session
from services.ui_style import apply_app_styles


def _avatar_html(username: str, *, large: bool = False) -> str:
    avatar = get_account_avatar(st.session_state)
    size_class = " account-avatar-large" if large else ""
    if avatar:
        encoded = base64.b64encode(avatar).decode("ascii")
        return (
            f'<img class="account-avatar{size_class}" '
            f'src="data:image/png;base64,{encoded}" alt="Your avatar">'
        )
    return (
        f'<span class="account-avatar account-avatar-initial{size_class}" '
        f'aria-label="Default avatar">{escape(username[:1].upper())}</span>'
    )


def _upload_avatar(upload_key: str, owner_id: str) -> None:
    uploaded = st.session_state.get(upload_key)
    if uploaded is None:
        return
    result = save_account_avatar(
        st.session_state, uploaded.getvalue(), expected_user_id=owner_id,
    )
    # Do not restore state after expiry or an account change during a callback.
    user = current_user(st.session_state)
    if user is not None and user.user_id == owner_id:
        st.session_state["account_avatar_notice"] = result


def _remove_avatar(owner_id: str) -> None:
    result = remove_account_avatar(st.session_state, expected_user_id=owner_id)
    user = current_user(st.session_state)
    if user is not None and user.user_id == owner_id:
        st.session_state["account_avatar_upload_version"] = (
            st.session_state.get("account_avatar_upload_version", 0) + 1
        )
        st.session_state["account_avatar_notice"] = result


def render_account_sidebar(account_page) -> None:
    user = current_user(st.session_state)
    if user is None:
        return
    with st.sidebar, st.container(key="account_sidebar"):
        st.markdown(
            '<div class="account-sidebar-identity">'
            f'{_avatar_html(user.username)}'
            '<div class="account-sidebar-copy">'
            '<span class="account-sidebar-label">SIGNED IN AS</span>'
            f'<strong>{escape(user.username)}</strong>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        st.page_link(
            account_page, label="My account", icon=":material/account_circle:",
            use_container_width=True,
        )
        st.button(
            "Log out", key="logout_button", icon=":material/logout:",
            on_click=logout_session, args=(st.session_state,),
            use_container_width=True,
        )


def render_account_page() -> None:
    user = current_user(st.session_state)
    if user is None:
        st.info("Log in to view your account.")
        st.stop()

    apply_app_styles()
    st.title("My account")
    st.caption("Your identity across your study and practice pages.")
    identity, avatar_controls = st.columns([1, 1], gap="large")
    with identity, st.container(border=True, key="account_identity"):
        st.markdown(_avatar_html(user.username, large=True), unsafe_allow_html=True)
        st.subheader(user.username)
        st.caption("Currently signed in")
        with st.expander("Account details"):
            st.text("Account ID")
            st.text(user.user_id)
        st.button(
            "Log out", key="account_logout_button", icon=":material/logout:",
            on_click=logout_session, args=(st.session_state,),
            use_container_width=True,
        )

    with avatar_controls, st.container(border=True, key="account_avatar_controls"):
        st.subheader("Profile photo")
        st.caption("Upload a PNG or JPG, up to 2 MB.")
        version = st.session_state.get("account_avatar_upload_version", 0)
        upload_key = f"account_avatar_upload_{user.user_id}_{version}"
        st.file_uploader(
            "Choose a profile photo", type=["png", "jpg", "jpeg"],
            max_upload_size=2, key=upload_key,
            on_change=_upload_avatar, args=(upload_key, user.user_id),
        )
        notice = st.session_state.get("account_avatar_notice")
        if notice:
            (st.success if notice.success else st.error)(notice.message)
        st.button(
            "Remove photo", key="account_remove_avatar",
            icon=":material/delete:", disabled=get_account_avatar(st.session_state) is None,
            on_click=_remove_avatar, args=(user.user_id,),
        )
        st.caption("Your photo stays in this browser session and clears when you log out.")
