"""Small edge-aligned buttons that open a page of their own.

Use these instead of an expander for secondary material. The button sits on
the left or the right edge, never full width and never in the middle, and the
page it opens shows only that material plus a way back.
"""
import streamlit as st

ALIGNMENTS = ("left", "right")


def open_page_button(label: str, page: str, *, key: str, icon: str | None = None,
                     align: str = "left", help: str | None = None) -> None:
    """One small button on the left or right edge; a click opens `page`.

    `label` and `help` are shown as given, so pass them through tr() first.
    """
    if align not in ALIGNMENTS:
        raise ValueError("A page link sits on the left or the right edge, never in the middle.")
    with st.container(horizontal=True, horizontal_alignment=align, key=f"page_link_{key}"):
        if st.button(label, key=key, icon=icon, help=help):
            st.switch_page(page)


def back_button(label: str, page: str, *, key: str) -> None:
    """The way back from a focus page: top-left, with a back arrow."""
    open_page_button(label, page, key=key, icon=":material/arrow_back:", align="left")
