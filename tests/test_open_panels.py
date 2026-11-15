"""Results, charts and the first step of a flow are on the page, not behind a click.

Home's study totals and supported-materials note, the Knowledge Map's Learning
Radar and the Concept Lab's prediction step and comparison table used to sit in
expanders. Maintenance tools, long raw text and the "Why ...?" explanations
(revealed after a prediction on purpose) stay folded.
"""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import Question, StudyPackage
from services import learning_radar, ui_style
from services.i18n import LANGUAGE_KEY
from services.learning_flow import open_lab
from tests.auth_helpers import TEST_USER, signed_in_app
from tests.test_knowledge_graph import RadarFake, _calculus_course, _topic

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "pages" / "0_Dashboard.py"
KNOWLEDGE_MAP = ROOT / "pages" / "4_Knowledge_Graph.py"
CONCEPT_LAB = ROOT / "pages" / "6_Concept_Lab.py"
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
    "Use UTF-8 TXT, text-based PDF or PPTX, or clear images of English text. "
    "Image text extraction requires Tesseract with English language support; "
    "scanned PDF OCR, PPTX slide notes and DOCX are not supported."
)
SUPPORTED_MATERIALS_ZH = (
    "使用 UTF-8 TXT、文字型 PDF/PPTX 或清晰的英文图片。"
    "图片文字提取需要支持英文的 Tesseract；暂不支持扫描 PDF 的 OCR、PPTX 备注或 DOCX。"
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
        order.index("dashboard_learning_dna")
        < order.index("dashboard_overview")
        < order.index("dashboard_courses_header")
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
    # At most two sentences, and still everything the expander said.
    assert len(re.findall(r"[.!?](?:\s|$)", SUPPORTED_MATERIALS)) == 2
    for fact in (
        "UTF-8 TXT", "text-based PDF or PPTX", "clear images of English text",
        "Image text extraction requires Tesseract with English language support",
        "scanned PDF OCR", "PPTX slide notes", "DOCX are not supported",
    ):
        assert fact in SUPPORTED_MATERIALS


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
    labels = [item.label for item in app.metric]
    assert labels == [label for label, _ in STUDY_TOTALS_ZH]
    # File formats and the OCR engine are names, not English UI text.
    assert _english_words(
        [SUPPORTED_MATERIALS_ZH, *labels],
        allowed=("UTF", "TXT", "PDF", "PPTX", "Tesseract", "OCR", "DOCX"),
    ) == []


# ---- Knowledge Map ----------------------------------------------------------------

def _knowledge_map(*, chinese=False, signed_in=False, focus=None) -> AppTest:
    app = signed_in_app(KNOWLEDGE_MAP) if signed_in else AppTest.from_file(str(KNOWLEDGE_MAP))
    app.session_state[LANGUAGE_KEY] = chinese
    course = _calculus_course()
    app.session_state["current_course"] = course
    if focus is not None:
        app.session_state[f"graph_pending_focus_{course.course_id}"] = focus
    return app.run()


def _panel_markdown(app: AppTest) -> list[str]:
    return [item.value for item in _block(app, "learning_radar_panel").markdown]


def _panel_captions(app: AppTest) -> list[str]:
    return [item.value for item in _block(app, "learning_radar_panel").caption]


def test_learning_radar_is_open_under_its_own_heading(monkeypatch):
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=3, sample=5), _topic("calc_limits", real=2)],
        has_sample=True,
    )

    app = _knowledge_map()

    assert not app.exception
    assert "Learning Radar · community signals" not in _expander_labels(app)
    assert app.expander == []
    # The bordered card sits under the graph, with nothing folded around it.
    assert "expander" not in _wrappers(app, "learning_radar_panel")
    panel = _block(app, "learning_radar_panel")
    assert panel.proto.flex_container.border
    content = _children(panel)
    assert content[0].type == "markdown" and content[0].value == "#### Learning Radar"
    # Everything that was inside the expander, in the same order.
    assert [child.type for child in content] == [
        "markdown", "caption", "flex_container", "markdown", "caption",
    ]
    assert content[1].value == "Topics where students marked \"I'm stuck here\", most flagged first."
    assert _key(content[2]) == "learning_radar_panel_chart"
    assert '<div class="paper-radar">' in content[2].markdown[0].value
    assert [item.value for item in content[2].caption] == ["Students stuck per topic"]
    assert content[3].value == (
        "1. **Derivatives** — 8 students are stuck here\n"
        "2. **Limits** — 2 students are stuck here"
    )
    assert content[4].value == "Includes sample data"


def test_learning_radar_keeps_the_privacy_rule_when_open(monkeypatch):
    hidden = learning_radar.TopicRadar(
        topic_id="calc_limits", real_count=2, sample_count=0,
        reasons={"concept": 2}, display_count=None,
    )
    RadarFake(monkeypatch, [hidden], has_sample=False)

    app = _knowledge_map()

    assert not app.exception
    shown = _panel_markdown(app) + _panel_captions(app)
    assert "1. **Limits** — Some students flagged this" in shown
    # Neither the hidden count nor its reasons appear, and there is no sample note.
    assert not any("2 student" in value or "Concept unclear" in value for value in shown)
    assert "Includes sample data" not in shown


def test_marking_and_unmarking_a_topic_updates_the_open_ranking(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])
    flag = f"radar_flag_{CALCULUS_ID}_calc_derivatives"

    app = _knowledge_map(signed_in=True, focus="calc_derivatives")
    assert not app.exception
    assert "1. **Derivatives** — 4 students are stuck here" in _panel_markdown(app)

    app.button(key=f"{flag}_no_reason").click().run()
    assert not app.exception
    assert radar.calls["set_flag"] == [(TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")]
    assert "1. **Derivatives** — 5 students are stuck here" in _panel_markdown(app)

    app.button(key=f"{flag}_clear").click().run()
    assert not app.exception
    assert radar.calls["clear_flag"] == [(TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")]
    assert "1. **Derivatives** — 4 students are stuck here" in _panel_markdown(app)
    assert app.expander == []


def test_learning_radar_panel_has_no_english_in_chinese(monkeypatch):
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=3, sample=5), _topic("calc_limits", real=2, display=None)],
        has_sample=True,
    )

    app = _knowledge_map(chinese=True)

    assert not app.exception
    markdown = _panel_markdown(app)
    captions = _panel_captions(app) + [
        item.value for item in _block(app, "learning_radar_panel_chart").caption
    ]
    assert markdown[0] == "#### 学习雷达"
    assert "包含示例数据" in captions and "各知识点卡住的学生人数" in captions
    ranking = markdown[-1]
    assert "8 名学生在这里遇到困难" in ranking and "有学生标记了此知识点" in ranking
    # Topic names are course content; the chart itself is markup.
    topic_names = [topic.name for topic in _calculus_course().topics]
    texts = [value for value in markdown if not value.lstrip().startswith("<")] + captions
    assert _english_words(texts, allowed=topic_names) == []


# ---- Concept Lab ------------------------------------------------------------------

LAB_TOPICS = ("limits", "derivatives", "corner")
WHY_EXPANDERS = [
    "Why can a missing point still have a limit?",
    "Why does the secant approach the tangent?",
    "Why is the corner continuous but not differentiable?",
]


def _lab(chinese: bool = False, **state) -> AppTest:
    app = AppTest.from_file(str(CONCEPT_LAB))
    app.session_state[LANGUAGE_KEY] = chinese
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


@pytest.mark.parametrize("tab_index,topic", list(enumerate(LAB_TOPICS)))
def test_predict_step_is_an_open_bordered_step_in_each_tab(tab_index, topic):
    app = _lab()

    assert not app.exception
    assert "1 · Predict before exploring" not in _expander_labels(app)
    step = _block(app, f"lab_{topic}_predict_step")
    assert step.proto.flex_container.border
    # In its tab and the controls column, not inside an expander.
    assert _wrappers(app, f"lab_{topic}_predict_step") == (
        "tab_container", "tab", "flex_container", "column",
    )
    assert _find(app.tabs[tab_index], f"lab_{topic}_predict_step") is not None
    content = _children(step)
    assert content[0].type == "markdown"
    assert content[0].value == "**1 · Predict before exploring**"
    assert [child.type for child in content[1:3]] == ["radio", "button"]
    assert content[1].key == f"lab_{topic}_prediction"
    assert content[2].key == f"lab_{topic}_check"


def test_prediction_check_still_works_in_the_open_step():
    app = _lab()
    app.radio(key="lab_derivatives_prediction").set_value("Always zero").run()
    app.button(key="lab_derivatives_check").click().run()

    assert not app.exception
    step = _block(app, "lab_derivatives_predict_step")
    assert any("horizontal line" in item.value for item in step.info)
    app.radio(key="lab_derivatives_prediction").set_value("The tangent slope at x₀").run()
    app.button(key="lab_derivatives_check").click().run()
    step = _block(app, "lab_derivatives_predict_step")
    assert any("Your prediction matches" in item.value for item in step.success)


def test_comparison_table_is_on_the_page_under_a_small_heading():
    app = _lab()

    assert not app.exception
    assert "Compare values from both sides" not in _expander_labels(app)
    limits = _children(app.tabs[0])
    types = [child.type for child in limits]
    heading = next(
        index for index, child in enumerate(limits)
        if child.type == "markdown" and child.value == "**Compare values from both sides**"
    )
    # The heading, then the table, then step 3 with its folded explanation.
    assert types[heading + 1] == "dataframe"
    assert limits[heading + 2].value == "**3 · Explain**"
    assert types[heading + 3] == "expander"
    table = limits[heading + 1].value
    assert list(table.columns) == ["Distance", "Left x", "f(Left x)", "Right x", "f(Right x)"]
    assert list(table["Distance"]) == [1, 0.5, 0.1, 0.05, 0.01, 0.001]


def test_why_explanations_stay_folded_and_unchanged():
    app = _lab()

    assert not app.exception
    assert _expander_labels(app) == WHY_EXPANDERS
    assert not any(item.proto.expanded for item in app.expander)


def test_tabs_and_sliders_still_work_with_the_open_panels():
    state = {}
    open_lab(state, CALCULUS_ID, "calc_derivatives")
    app = _lab(**state)

    assert not app.exception
    # The requested topic opens its tab, as before.
    assert app.get("tab_container")[0].proto.tab_container.default_tab_index == 1
    app.slider(key="concept_lab_x0").set_value(2.0).run()
    app.select_slider(key="concept_lab_h").set_value(0.001).run()
    assert not app.exception
    assert float(app.metric[3].value) == 7.0
    assert abs(float(app.metric[2].value) - 7.0) < 0.01
    app.select_slider(key="concept_lab_limit_distance").set_value(0.001).run()
    assert not app.exception
    assert float(app.metric[0].value) == pytest.approx(3.999)
    assert len(app.dataframe[0].value) == 6
    assert _block(app, "lab_limits_predict_step") is not None


def test_concept_lab_open_panels_have_no_english_in_chinese():
    app = _lab(chinese=True)

    assert not app.exception
    texts = []
    for topic in LAB_TOPICS:
        step = _block(app, f"lab_{topic}_predict_step")
        texts += [item.value for item in step.markdown]
        radio = app.radio(key=f"lab_{topic}_prediction")
        texts += [radio.label, *radio.options]
        texts.append(app.button(key=f"lab_{topic}_check").label)
    assert texts[0] == "**1 · 实验前先预测**"
    limits = _children(app.tabs[0])
    heading = [child.value for child in limits if child.type == "markdown" and "对比" in child.value]
    assert heading == ["**对比两侧数值**"]
    columns = list(app.dataframe[0].value.columns)
    assert columns == ["距离", "左侧 x", "左侧 f(x)", "右侧 x", "右侧 f(x)"]
    # Single letters are mathematics (x, f, h); words would be English UI text.
    assert _english_words([*texts, *heading, *columns]) == []


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


def test_learning_radar_heading_keeps_its_gap_to_the_caption():
    css = PANELS_CSS.read_text(encoding="utf-8")
    panel = '[data-testid="stMain"] .st-key-learning_radar_panel'

    assert "var(--font-title)" in _rule(css, f"{panel} h4")
    assert "margin-bottom: 0;" in _rule(
        css, f'{panel} [data-testid="stMarkdownContainer"]:has(h4)'
    )
