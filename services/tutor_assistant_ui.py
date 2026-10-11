"""Global floating Tutor UI, backed by server-owned course and session state."""

from functools import lru_cache
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components

from services.auth_session import current_user
from services.tutor_assistant_state import (
    assistant_view,
    clear_conversation,
    submit_question,
)

COMPONENT_KEY = "floating_tutor"
ASSETS = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=1)
def _component():
    mascot = base64.b64encode((ASSETS / "pilot-book-mascot.png").read_bytes()).decode("ascii")
    html = (ASSETS / "tutor_assistant.html").read_text(encoding="utf-8").replace(
        "__PILOT_MASCOT_DATA_URI__", f"data:image/png;base64,{mascot}",
    )
    return components.component(
        "exampilot_floating_tutor",
        html=html,
        css=(ASSETS / "tutor_assistant.css").read_text(encoding="utf-8"),
        js=(ASSETS / "tutor_assistant.js").read_text(encoding="utf-8"),
        isolate_styles=True,
    )


@lru_cache(maxsize=1)
def _cleanup_component():
    """Register a JS-only cleanup hook, never the unauthenticated Tutor UI."""
    return components.component(
        "exampilot_tutor_session_cleanup",
        js="""
export default function() {
  if (typeof window.__examPilotFloatingTutor?.reset === 'function') {
    window.__examPilotFloatingTutor.reset();
  }
  delete window.__examPilotFloatingTutor;
}
""",
    )


def clear_tutor_browser_state() -> None:
    """Forget cached drafts/controls before displaying logged-out account forms."""
    _cleanup_component()(
        key="floating_tutor_session_cleanup",
        width="stretch",
        height=1,
    )


def render_tutor_assistant() -> None:
    """Mount for a live account, including empty authenticated study pages."""
    user = current_user(st.session_state)
    if user is None or not isinstance(user.user_id, str) or not user.user_id.strip():
        return

    def on_submit() -> None:
        callback_user = current_user(st.session_state)
        if (
            callback_user is None
            or not isinstance(callback_user.user_id, str)
            or not callback_user.user_id.strip()
        ):
            return
        value = st.session_state.get(COMPONENT_KEY)
        if value is not None:
            submit_question(
                st.session_state,
                st.session_state.get("current_course"),
                value.get("submit"),
                owner_id=callback_user.user_id,
            )

    def on_clear() -> None:
        callback_user = current_user(st.session_state)
        if (
            callback_user is None
            or not isinstance(callback_user.user_id, str)
            or not callback_user.user_id.strip()
        ):
            return
        value = st.session_state.get(COMPONENT_KEY)
        if value is not None:
            clear_conversation(
                st.session_state,
                st.session_state.get("current_course"),
                value.get("clear"),
                owner_id=callback_user.user_id,
            )

    _component()(
        key=COMPONENT_KEY,
        data=assistant_view(
            st.session_state,
            st.session_state.get("current_course"),
            owner_id=user.user_id,
        ),
        on_submit_change=on_submit,
        on_clear_change=on_clear,
        width="stretch",
        height=1,
    )
