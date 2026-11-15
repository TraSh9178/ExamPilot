"""Quiet, keyboard-focusable explanations shared by learning pages."""
from html import escape
from uuid import uuid4
from hashlib import sha256

import streamlit as st
from services.i18n import tr


def help_tip(text):
    """Show optional context on hover/focus; a tap focuses the native button."""
    identifier = 'help-' + uuid4().hex
    # Keep Markdown from inserting paragraph elements inside the HTML tooltip.
    content = escape(text).replace('\n\n', '<br><br>').replace('\n', '<br>')
    st.markdown(
        '<div class="quiet-help-row"><span class="quiet-help">'
        f'<button type="button" aria-label="{escape(tr("Help"), quote=True)}" '
        f'aria-describedby="{identifier}">?</button>'
        f'<span class="quiet-help-text" role="tooltip" id="{identifier}">{content}</span>'
        '</span></div>', unsafe_allow_html=True,
    )


def help_heading(title, text, *, level='subheader'):
    """One help target in the heading row, rather than an extra block of copy."""
    with st.container(horizontal=True, vertical_alignment='bottom', gap='small',
                      key='help_heading_' + sha256((title + text).encode()).hexdigest()[:12]):
        getattr(st, level)(title, width='stretch')
        with st.container(width='content'):
            help_tip(text)
