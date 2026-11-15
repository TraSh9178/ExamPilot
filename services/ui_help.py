"""Quiet, keyboard-focusable explanations shared by learning pages."""
from html import escape
from uuid import uuid4

import streamlit as st
from services.i18n import tr


def help_tip(text):
    """Show optional context on hover/focus; a tap focuses the native button."""
    identifier = 'help-' + uuid4().hex
    st.markdown(
        '<div class="quiet-help-row"><span class="quiet-help">'
        f'<button type="button" aria-label="{escape(tr("Help"), quote=True)}" '
        f'aria-describedby="{identifier}">?</button>'
        f'<span class="quiet-help-text" role="tooltip" id="{identifier}">{escape(text)}</span>'
        '</span></div>', unsafe_allow_html=True,
    )
