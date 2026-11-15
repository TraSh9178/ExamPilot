"""Small edge-aligned buttons that open a page of their own.

Use these instead of an expander for secondary material. The button sits on
the left or the right edge, never full width and never in the middle, and the
page it opens shows only that material plus a way back.
"""
import streamlit as st

ALIGNMENTS = ("left", "right")


def _keep_values(names: tuple[str, ...]) -> None:
    """Runs on the click, before the page is drawn again.

    Streamlit forgets a widget's value once the page that drew it is left;
    setting it again here carries it over to a page that uses the same key.
    """
    for name in names:
        if name in st.session_state:
            st.session_state[name] = st.session_state[name]


def open_page_button(label: str, page: str, *, key: str, icon: str | None = None,
                     align: str = "left", help: str | None = None,
                     keep: tuple[str, ...] = ()) -> None:
    """One small button on the left or right edge; a click opens `page`.

    `label` and `help` are shown as given, so pass them through tr() first.
    `keep` names widget keys whose values the opened page should still see.
    """
    if align not in ALIGNMENTS:
        raise ValueError("A page link sits on the left or the right edge, never in the middle.")
    with st.container(horizontal=True, horizontal_alignment=align, key=f"page_link_{key}"):
        if keep:
            clicked = st.button(label, key=key, icon=icon, help=help,
                                on_click=_keep_values, args=(tuple(keep),))
        else:
            clicked = st.button(label, key=key, icon=icon, help=help)
        if clicked:
            st.switch_page(page)


def back_button(label: str, page: str, *, key: str, keep: tuple[str, ...] = ()) -> None:
    """The way back from a focus page: top-left, with a back arrow."""
    open_page_button(label, page, key=key, icon=":material/arrow_back:", align="left", keep=keep)
