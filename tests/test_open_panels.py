"""Home's figures and notes are on the page; the Knowledge Map is only the map.

Home's study totals and supported-materials note used to sit in expanders.
The Knowledge Map's Learning Radar panel is gone: a small right-edge button
opens the Learning Radar page, which has the chart, ranking and stuck buttons.
The Concept Lab's steps are tested in tests/test_concept_lab_steps.py.
"""

import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import Question, StudyPackage
from services import ui_style
from services.i18n import LANGUAGE_KEY
from tests.auth_helpers import TEST_USER, signed_in_app
from tests.test_knowledge_graph import RadarFake, _calculus_course, _other_course, _topic

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "pages" / "0_Dashboard.py"
KNOWLEDGE_MAP = ROOT / "pages" / "4_Knowledge_Graph.py"
PANELS_CSS = ROOT / "assets" / "paper_panels.css"
CALCULUS_ID = "calculus-i-demo"

# Two or more Latin letters in a row: an English word left in a Chinese page.
ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")


# ---- Helpers that read the rendered page ---------------------------------------

def _key(node) -> str:
    """The user key of a keyed block ("$$ID-<hash>-<key>"), else ""."""
    block_id = getattr(node.proto, "id", "") if isinstance(node, Block) and node.proto is not None else ""
    return block_id.split("-", 2)[2] if block_id else ""


def _find(node, key: str):
    """The keyed block, and the types of the blocks it sits in (outermost first)."""
    for child in node.children.values():
        if not isinstance(child, Block):
            continue
        if _key(child) == key:
            return child, ()
        found = _find(child, key)
        if found is not None:
            block, trail = found
            return block, (child.type, *trail)
    return None


def _block(app: AppTest, key: str) -> Block:
    found = _find(app.main, key)
    assert found is not None, key
    return found[0]


def _wrappers(app: AppTest, key: str) -> tuple[str, ...]:
    found = _find(app.main, key)
    assert found is not None, key
    return found[1]


def _children(block: Block) -> list:
    return list(block.children.values())


def _expander_labels(app: AppTest) -> list[str]:
    return [item.label for item in app.expander]


def _top_level_keys(app: AppTest) -> list[str]:
    return [_key(child) for child in app.main.children.values() if _key(child)]


def _english_words(texts, *, allowed=()) -> list[str]:
    words = []
    for text in texts:
        for name in allowed:
            text = text.replace(name, " ")
        words += ENGLISH_WORD.findall(text)
    return words


# ---- Home -------------------------------------------------------------------------

def _biology() -> StudyPackage:
    return StudyPackage(
        course_id="my-course",
        course_name="Biology",
        topics=[{"id": "t1", "name": "Cells", "summary": "Summary."}],
        relationships=[],
        questions=[
            Question(
                id="q1", topic_id="t1", question="Question?",
                options=["a", "b", "c", "d"], correct_index=0, explanation="Because.",
            )
        ],
    )


def _home(chinese: bool = False, **state) -> AppTest:
    app = AppTest.from_file(str(DASHBOARD))
    app.session_state[LANGUAGE_KEY] = chinese
    app.session_state["courses"] = [_biology()]
    app.session_state["current_course"] = None
    # Two saved sessions in the student's course and one in a demo course.
    app.session_state["practice_history_my-course"] = {"s1": {}, "s2": {}}
    app.session_state[f"practice_history_{CALCULUS_ID}"] = {"s3": {}}
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


# Read from the "Study totals" expander at 184c1f5 for the state above:
# Biology plus the three built-in demo courses; 1 + 3 + 15 + 3 topics.
STUDY_TOTALS = [("Courses", "4"), ("Knowledge points", "22"), ("Practice sessions", "3")]
STUDY_TOTALS_ZH = [("课程", "4"), ("知识点", "22"), ("练习次数", "3")]

SUPPORTED_MATERIALS = (
    "Use UTF-8 TXT, text-based PDF or PPTX, or clear images of English text; "
    "reading text from images may not always be available. "
    "Scanned PDFs, PPTX slide notes and DOCX files are not supported."
)
SUPPORTED_MATERIALS_ZH = (
    "使用 UTF-8 TXT、文字型 PDF/PPTX 或清晰的英文图片；图片中的文字有时可能无法读取。"
    "暂不支持扫描版 PDF、PPTX 备注或 DOCX 文件。"
)


@pytest.mark.parametrize("chinese,totals", [(False, STUDY_TOTALS), (True, STUDY_TOTALS_ZH)])
def test_home_study_totals_are_tiles_on_the_page_with_the_same_figures(chinese, totals):
    app = _home(chinese)

    assert not app.exception
    assert app.expander == []
    overview = _block(app, "dashboard_overview")
    # Straight on the page, where the expander was: after Learning DNA, before My courses.
    assert _wrappers(app, "dashboard_overview") == ()
    order = _top_level_keys(app)
    assert (
        order.index("dashboard_courses_header")
        < order.index("dashboard_overview")
        < order.index("dashboard_actions")
    )
    # One row of three tiles, each with its label.
    (row,) = _children(overview)
    assert row.type == "flex_container" and row.proto.flex_container.wrap
    columns = _children(row)
    assert [column.type for column in columns] == ["column"] * 3
    tiles = [_children(column) for column in columns]
    assert all(len(tile) == 1 and tile[0].type == "metric" for tile in tiles)
    assert [(tile[0].label, tile[0].value) for tile in tiles] == totals
    assert [(item.label, item.value) for item in app.metric] == totals


def test_home_study_totals_follow_new_practice():
    app = _home()
    app.session_state["practice_history_my-course"] = {"s1": {}, "s2": {}, "s4": {}}
    app.run()

    assert not app.exception
    assert [(item.label, item.value) for item in app.metric][2] == ("Practice sessions", "4")


def _open_setup(chinese: bool = False, document: dict | None = None) -> AppTest:
    state = {"show_course_setup": True}
    if document is not None:
        # No file in the uploader, so the saved document belongs to "no file".
        state.update(setup_document=document, setup_document_source=None)
    return _home(chinese, **state)


def test_home_supported_materials_is_a_visible_caption_of_two_sentences():
    app = _open_setup()

    assert not app.exception
    assert "Supported materials" not in _expander_labels(app)
    setup = _block(app, "dashboard_course_setup")
    captions = [item.value for item in setup.caption]
    assert SUPPORTED_MATERIALS in captions
    # Right under the formats line, where the expander was.
    formats = captions.index(
        "PDF, PPTX, TXT, PNG or JPG/JPEG · up to 5 MiB per file · "
        "up to 50,000 characters of extracted text."
    )
    assert captions[formats + 1] == SUPPORTED_MATERIALS
    # At most two sentences, and what the student needs to know.
    assert len(re.findall(r"[.!?](?:\s|$)", SUPPORTED_MATERIALS)) == 2
    for fact in (
        "UTF-8 TXT", "text-based PDF or PPTX", "clear images of English text",
        "reading text from images may not always be available",
        "Scanned PDFs", "PPTX slide notes", "DOCX files are not supported",
    ):
        assert fact in SUPPORTED_MATERIALS
    # No server details: the OCR engine is not named.
    assert not any("Tesseract" in value or "OCR" in value for value in captions)


def test_home_long_extracted_text_stays_folded():
    document = {
        "ok": True,
        "text": "Cells are the basic unit of life. " * 40,
        "filename": "notes.txt",
        "sources": [{"filename": "notes.txt", "page": None}],
    }
    app = _open_setup(document=document)

    assert not app.exception
    assert _expander_labels(app) == ["Preview extracted text"]
    preview = app.expander[0]
    assert not preview.proto.expanded
    assert preview.text[0].value.strip() == document["text"].strip()


def test_home_open_panels_have_no_english_in_chinese():
    app = _open_setup(chinese=True)

    assert not app.exception
    captions = [item.value for item in _block(app, "dashboard_course_setup").caption]
    assert SUPPORTED_MATERIALS_ZH in captions
    assert SUPPORTED_MATERIALS not in captions
    assert len(re.findall(r"。", SUPPORTED_MATERIALS_ZH)) == 2
    assert not any("Tesseract" in value or "OCR" in value for value in captions)
    labels = [item.label for item in app.metric]
    assert labels == [label for label, _ in STUDY_TOTALS_ZH]
    # File formats are names, not English UI text.
    assert _english_words(
        [SUPPORTED_MATERIALS_ZH, *labels], allowed=("UTF", "TXT", "PDF", "PPTX", "DOCX"),
    ) == []


# ---- Knowledge Map ----------------------------------------------------------------

def _knowledge_map(*, chinese=False, signed_in=False, focus=None, course=None) -> AppTest:
    app = signed_in_app(KNOWLEDGE_MAP) if signed_in else AppTest.from_file(str(KNOWLEDGE_MAP))
    app.session_state[LANGUAGE_KEY] = chinese
    course = course or _calculus_course()
    app.session_state["current_course"] = course
    if focus is not None:
        app.session_state[f"graph_pending_focus_{course.course_id}"] = focus
    return app.run()


def _visible(app: AppTest) -> list[str]:
    texts = [item.value for item in app.markdown if not item.value.lstrip().startswith("<style")]
    texts += [item.value for kind in ("caption", "subheader", "info") for item in app.get(kind)]
    return texts


def test_knowledge_map_has_no_radar_panel_and_a_right_edge_link_to_the_radar_page(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=3, sample=5), _topic("calc_limits", real=2)],
        has_sample=True,
    )

    app = _knowledge_map()

    assert not app.exception
    assert _find(app.main, "learning_radar_panel") is None
    assert _find(app.main, "learning_radar_panel_chart") is None
    shown = _visible(app)
    assert not any("Learning Radar" in value or "<svg" in value for value in shown)
    assert not any(value.startswith("1. ") for value in shown)
    for gone in ("Includes sample data", "Students stuck per topic",
                 "Topics where students marked \"I'm stuck here\", most flagged first."):
        assert gone not in shown
    assert app.expander == []

    # Under the map, in the graph column, pushed to the right edge.
    holder = _block(app, "page_link_knowledge_map_learning_radar")
    assert holder.proto.flex_container.justify == BlockProto.FlexContainer.Justify.JUSTIFY_END
    trail = _wrappers(app, "page_link_knowledge_map_learning_radar")
    assert trail == ("flex_container", "column")
    graph_column = _find(app.main, "knowledge_graph_canvas")
    assert graph_column is not None and graph_column[1] == trail
    link = app.button(key="knowledge_map_learning_radar")
    assert link.label == "Learning Radar"
    assert link.proto.icon == ":material/radar:"
    assert [button.label for button in holder.button] == ["Learning Radar"]

    link.click().run()
    assert destinations == ["pages/7_Learning_Radar.py"]


def test_no_radar_link_for_a_course_without_the_radar(monkeypatch):
    RadarFake(monkeypatch, [_topic("topic-1", real=9)], enabled=False)

    app = _knowledge_map(course=_other_course())

    assert not app.exception
    assert _find(app.main, "page_link_knowledge_map_learning_radar") is None
    assert not any(button.key == "knowledge_map_learning_radar" for button in app.button)


def test_badges_and_the_selected_topic_stuck_buttons_still_work(monkeypatch):
    from components import knowledge_graph

    rendered = []
    monkeypatch.setattr(
        knowledge_graph, "agraph",
        lambda nodes, edges, config, node_scale: rendered.append(nodes) or None,
    )
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])
    flag = f"radar_flag_{CALCULUS_ID}_calc_derivatives"

    app = _knowledge_map(signed_in=True, focus="calc_derivatives")
    assert not app.exception
    assert {node.id: node.label for node in rendered[-1]}["calc_derivatives"] == "Derivatives\n🔥 4 stuck"
    assert "4 students are stuck here" in _visible(app)

    app.button(key=f"{flag}_no_reason").click().run()
    assert not app.exception
    assert radar.calls["set_flag"] == [(TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")]
    assert "5 students are stuck here" in _visible(app)
    assert {node.id: node.label for node in rendered[-1]}["calc_derivatives"] == "Derivatives\n🔥 5 stuck"

    app.button(key=f"{flag}_clear").click().run()
    assert not app.exception
    assert radar.calls["clear_flag"] == [(TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")]
    assert "4 students are stuck here" in _visible(app)
    # The Concept Lab link stays in the topic's details, and so does the radar link.
    assert app.button(key=f"radar_concept_lab_{CALCULUS_ID}_calc_derivatives").label == "Open Concept Lab"
    assert app.button(key="knowledge_map_learning_radar").label == "Learning Radar"


def test_radar_link_is_chinese_with_the_chinese_interface(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", real=3, sample=5)], has_sample=True)

    app = _knowledge_map(chinese=True)

    assert not app.exception
    assert app.button(key="knowledge_map_learning_radar").label == "学习雷达"
    assert _english_words([app.button(key="knowledge_map_learning_radar").label]) == []


# ---- Styles ----------------------------------------------------------------------

def _rule(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r" \{\n(.*?)\n\s*\}", css, re.DOTALL)
    assert match, selector
    return match.group(1)


def test_home_tiles_wrap_two_to_a_row_on_narrow_screens_using_paper_tokens():
    css = PANELS_CSS.read_text(encoding="utf-8")
    overview = '[data-testid="stMain"] .st-key-dashboard_overview'

    # The sheet is loaded with the other paper sheets, after academic_ui.css.
    assert PANELS_CSS in ui_style.paper_stylesheets()
    tile = _rule(css, f'{overview} [data-testid="stMetric"]')
    assert "var(--paper-card)" in tile and "var(--paper-line)" in tile
    # Colours come from the paper tokens only.
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(", css)
    narrow = css[css.index("@media (max-width: 759.98px) {"):]
    narrow = narrow[:narrow.index("\n}\n")]
    row = _rule(narrow, f'{overview} [data-testid="stHorizontalBlock"]')
    assert "flex-direction: row;" in row and "flex-wrap: wrap;" in row
    column = _rule(narrow, f'{overview} [data-testid="stColumn"]')
    assert "flex: 1 1 calc(50% - .5rem) !important;" in column
    assert "width: calc(50% - .5rem) !important;" in column
    assert "min-width: 0;" in column
    # Labels wrap rather than run out of a narrow tile.
    label = _rule(css, f'{overview} [data-testid="stMetricLabel"] :is(div, p)')
    assert "white-space: normal;" in label and "overflow-wrap: anywhere;" in label


def test_rules_for_the_removed_radar_panel_are_gone():
    css = PANELS_CSS.read_text(encoding="utf-8")

    assert "learning_radar_panel" not in css
    # The Learning Radar page keeps its own containers, which this sheet never styled.
    radar_page = (ROOT / "pages" / "7_Learning_Radar.py").read_text(encoding="utf-8")
    for key in re.findall(r'key="(learning_radar_[a-z_]+)"', radar_page):
        assert key not in css
