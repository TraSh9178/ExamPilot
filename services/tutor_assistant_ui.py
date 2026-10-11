"""Global floating Tutor UI, backed by server-owned course and session state."""

from functools import lru_cache
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components

from services.tutor_assistant_state import (
    assistant_view,
    clear_conversation,
    submit_question,
)

COMPONENT_KEY = "floating_tutor"
ASSETS = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=1)
def _component():
    return components.component(
        "exampilot_floating_tutor",
        html=(ASSETS / "tutor_assistant.html").read_text(encoding="utf-8"),
        css=(ASSETS / "tutor_assistant.css").read_text(encoding="utf-8"),
        js=(ASSETS / "tutor_assistant.js").read_text(encoding="utf-8"),
        isolate_styles=True,
    )


def render_tutor_assistant() -> None:
    """Mount before page execution so empty pages using st.stop keep the Tutor."""

    def on_submit() -> None:
        value = st.session_state.get(COMPONENT_KEY)
        if value is not None:
            submit_question(
                st.session_state,
                st.session_state.get("current_course"),
                value.get("submit"),
            )

    def on_clear() -> None:
        value = st.session_state.get(COMPONENT_KEY)
        if value is not None:
            clear_conversation(
                st.session_state,
                st.session_state.get("current_course"),
                value.get("clear"),
            )

    _component()(
        key=COMPONENT_KEY,
        data=assistant_view(
            st.session_state,
            st.session_state.get("current_course"),
        ),
        on_submit_change=on_submit,
        on_clear_change=on_clear,
        width="stretch",
        height=1,
    )
