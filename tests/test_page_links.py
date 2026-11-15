"""Focus pages and the small edge-aligned buttons that open them."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from services import page_registry
from services.i18n import _TRANSLATIONS


ROOT = Path(__file__).resolve().parents[1]


def test_registry_entries_are_distinct_page_files_with_translated_titles():
    paths = [path for path, _, _ in page_registry.FOCUS_PAGES]
    urls = [url for _, _, url in page_registry.FOCUS_PAGES]
    assert len(set(paths)) == len(paths) and len(set(urls)) == len(urls)
    assert all(path.startswith("pages/") and path.endswith(".py") for path in paths)
    for _, title, _ in page_registry.FOCUS_PAGES:
        assert title in _TRANSLATIONS, f"{title} has no Chinese title"


def test_only_pages_whose_files_exist_are_registered(tmp_path):
    assert page_registry.existing_focus_pages(tmp_path) == []
    first, second = page_registry.FOCUS_PAGES[0], page_registry.FOCUS_PAGES[2]
    for path, _, _ in (second, first):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("", encoding="utf-8")
    # Registry order, whatever order the files appeared in.
    assert page_registry.existing_focus_pages(tmp_path) == [first, second]
    assert page_registry.existing_focus_pages() == [
        entry for entry in page_registry.FOCUS_PAGES if (ROOT / entry[0]).is_file()
    ]


def _link_script(align):
    # AppTest runs this function's source as a script, so everything it needs
    # is imported inside it and the alignment arrives as an argument.
    from components.page_links import back_button, open_page_button

    open_page_button(
        "Practice history", "pages/8_Practice_History.py", key="open_history",
        icon=":material/history:", align=align,
    )
    back_button("Back to Practice", "pages/2_Practice_Center.py", key="back_to_practice")


@pytest.mark.parametrize("align", ["left", "right"])
def test_page_link_is_a_small_button_on_one_edge(monkeypatch, align):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    app = AppTest.from_function(_link_script, kwargs={"align": align}).run()

    assert not app.exception
    assert [button.label for button in app.button] == ["Practice history", "Back to Practice"]
    holders = {
        child.proto.id.rsplit("-", 1)[-1]: child.proto.flex_container
        for child in app.main.children.values()
        if isinstance(child, Block) and child.proto is not None
    }
    assert set(holders) == {"page_link_open_history", "page_link_back_to_practice"}
    opened, back = holders["page_link_open_history"], holders["page_link_back_to_practice"]
    # Both are horizontal rows; the first is pushed to the requested edge and
    # the way back always starts from the left, so the two differ only on the right.
    assert opened.direction == back.direction
    assert (opened.justify == back.justify) == (align == "left")

    app.button(key="open_history").click().run()
    app.button(key="back_to_practice").click().run()
    assert destinations == ["pages/8_Practice_History.py", "pages/2_Practice_Center.py"]


def test_page_link_refuses_the_middle():
    from components.page_links import open_page_button

    with pytest.raises(ValueError):
        open_page_button("Practice history", "pages/8_Practice_History.py", key="x", align="center")


def test_page_link_buttons_are_styled_small_and_never_full_width():
    css = (ROOT / "assets" / "paper_links.css").read_text(encoding="utf-8")
    assert '[class*="st-key-page_link_"] button' in css
    assert "width: 100%" not in css
