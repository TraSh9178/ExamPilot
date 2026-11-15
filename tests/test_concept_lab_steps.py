"""Concept Lab, one step at a time: predict, explore, explain.

Each tab keeps its chart on the right in every step; the left column shows
only the current step. Nothing here is graded, saved or sent anywhere.
"""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from services.concept_lab_ui import EXPLANATIONS, PREDICTIONS
from services.i18n import LANGUAGE_KEY
from tests.auth_helpers import signed_in_app

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "6_Concept_Lab.py"
TOPICS = ("limits", "derivatives", "corner")
TAB = {topic: index for index, topic in enumerate(TOPICS)}
PRACTICE = {
    "limits": "concept_lab_practice_calc_limits",
    "derivatives": "concept_lab_practice_calc_derivatives",
    "corner": "concept_lab_practice_calc_derivatives_corner",
}
EXPLORE = {
    "limits": {"concept_lab_limit_distance"},
    "derivatives": {"concept_lab_x0", "concept_lab_h", "concept_lab_side", "concept_lab_zoom", "lab_save_secant"},
    "corner": {"concept_lab_corner_h"},
}


def step_widgets(topic: str, step: int, *, checked: bool = False) -> set[str]:
    """The widget keys the left column holds in each step."""
    if step == 1:
        return {f"lab_{topic}_prediction", f"lab_{topic}_check"} | (
            {f"lab_{topic}_next_explore"} if checked else set()
        )
    if step == 2:
        return EXPLORE[topic] | {
            f"lab_{topic}_approach", f"lab_{topic}_reset",
            f"lab_{topic}_back_to_1", f"lab_{topic}_next_explain",
        }
    return {
        f"lab_{topic}_explanation", f"lab_{topic}_show_answer",
        f"lab_{topic}_back_to_2", f"lab_{topic}_start_again",
    }


# ---- Helpers ---------------------------------------------------------------------

def _lab(chinese: bool = False, **state) -> AppTest:
    # The first run in a fresh process imports the chart libraries; allow for it.
    app = AppTest.from_file(str(PAGE), default_timeout=15)
    app.session_state[LANGUAGE_KEY] = chinese
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


def _key(node) -> str:
    block_id = getattr(node.proto, "id", "") if isinstance(node, Block) and node.proto is not None else ""
    return block_id.split("-", 2)[2] if block_id else ""


def _walk(node):
    for child in node.children.values():
        yield child
        if isinstance(child, Block):
            yield from _walk(child)


def _columns(app: AppTest, topic: str) -> tuple[Block, Block]:
    """The tab's left (steps) and right (chart) columns."""
    tab = app.tabs[TAB[topic]]
    row = next(
        child for child in tab.children.values()
        if isinstance(child, Block) and [c.type for c in child.children.values()] == ["column", "column"]
    )
    left, right = row.children.values()
    return left, right


def _widget_keys(block: Block) -> set[str]:
    return {node.key for node in _walk(block) if not isinstance(node, Block) and getattr(node, "key", None)}


def _texts(block: Block) -> list[str]:
    texts = []
    for node in _walk(block):
        if isinstance(node, Block):
            continue
        if node.type in {"markdown", "caption", "subheader", "title", "info", "success", "warning", "error"}:
            texts.append(node.value)
        elif node.type in {"button", "text_area", "select_slider", "slider", "toggle", "metric"}:
            texts.append(node.label)
        elif node.type == "radio":
            texts += [node.label, *node.options]
    return texts


def _step(app: AppTest, topic: str) -> int:
    key = f"lab_{topic}_step"
    # A tab that was never moved has no step stored yet: it is on step 1.
    return app.session_state[key] if key in app.session_state else 1


def _indicator(block: Block) -> str:
    return next(node.value for node in _walk(block) if node.type == "markdown" and "lab-steps" in node.value)


def _check(app: AppTest, topic: str, choice: str) -> None:
    app.radio(key=f"lab_{topic}_prediction").set_value(choice).run()
    app.button(key=f"lab_{topic}_check").click().run()


def _explain_block(app: AppTest, topic: str) -> Block:
    return next(node for node in _walk(app.main) if _key(node) == f"lab_{topic}_explain")


def _answer_on_page(app: AppTest, topic: str) -> bool:
    _, formula, answer = EXPLANATIONS[topic]
    values = [
        node.value for node in _walk(app.main)
        if not isinstance(node, Block) and node.type in {"markdown", "latex", "caption", "info", "success", "text"}
    ]
    return any(answer in str(value) for value in values) or (
        formula is not None and any(formula in str(value) for value in values)
    )


def _no_expander_or_popover(app: AppTest) -> bool:
    types = {node.type for node in _walk(app.main)}
    return not app.expander and "expander" not in types and "popover" not in types


# ---- One step at a time ----------------------------------------------------------

def test_a_new_session_starts_every_tab_on_step_one():
    app = _lab()

    assert not app.exception
    for topic in TOPICS:
        assert _step(app, topic) == 1
        left, _ = _columns(app, topic)
        assert _widget_keys(left) == step_widgets(topic, 1)
        indicator = _indicator(left)
        assert re.search(r'<li class="lab-step is-current" aria-current="step">.*?1</span> Predict</li>', indicator)
        assert indicator.count('aria-current="step"') == 1
        assert "Explore" in indicator and "Explain" in indicator
    assert _no_expander_or_popover(app)


@pytest.mark.parametrize("topic", TOPICS)
@pytest.mark.parametrize("step", [1, 2, 3])
def test_each_step_shows_only_its_controls_beside_the_same_chart(topic, step):
    app = _lab(**{f"lab_{topic}_step": step})

    assert not app.exception
    left, right = _columns(app, topic)
    assert _widget_keys(left) == step_widgets(topic, step)
    # The indicator starts the column; prediction choices have their own panel.
    first = list(left.children.values())[0]
    assert first.type == "markdown" and "lab-steps" in first.value
    assert sum(
        bool(isinstance(node, Block) and getattr(getattr(node.proto, "flex_container", None), "border", False))
        for node in _walk(left)
    ) == (1 if step == 1 else 0)
    if step == 1:
        assert f"lab_{topic}_prediction" in {getattr(node, "key", None) for node in _walk(left)}
    # The other tabs stay on step 1.
    for other in TOPICS:
        if other != topic:
            assert _widget_keys(_columns(app, other)[0]) == step_widgets(other, 1)
    # The chart and its live figures are there in every step.
    assert [node.type for node in _walk(right) if node.type in {"vega_lite_chart", "arrow_vega_lite_chart"}]
    assert len([node for node in _walk(right) if node.type == "metric"]) == 2
    assert len(app.get("vega_lite_chart") or app.get("arrow_vega_lite_chart")) == 3
    assert len(app.metric) == 6
    names = re.findall(r"</span> (\w+)</li>", _indicator(left))
    assert names == ["Predict", "Explore", "Explain"]
    current = re.search(r'aria-current="step"><span class="lab-step-number">(\d)</span>', _indicator(left))
    assert current and int(current.group(1)) == step
    assert _no_expander_or_popover(app)


@pytest.mark.parametrize("value", [0, 4, -1, "2", None, True, 2.0])
def test_a_step_outside_one_to_three_counts_as_step_one(value):
    app = _lab(**{"lab_limits_step": value})

    assert not app.exception
    assert _widget_keys(_columns(app, "limits")[0]) == step_widgets("limits", 1)


# ---- Step 1: predict ------------------------------------------------------------

@pytest.mark.parametrize("topic", TOPICS)
def test_next_explore_appears_only_after_a_prediction_is_checked(topic):
    app = _lab()
    assert not any(button.key == f"lab_{topic}_next_explore" for button in app.button)

    radio = app.radio(key=f"lab_{topic}_prediction")
    assert radio.proto.horizontal is False
    assert app.button(key=f"lab_{topic}_check").proto.type == "primary"

    # Checking with no choice only asks for one.
    app.button(key=f"lab_{topic}_check").click().run()
    assert "Choose a prediction first." in [item.value for item in app.info]
    assert not any(button.key == f"lab_{topic}_next_explore" for button in app.button)

    _check(app, topic, PREDICTIONS[topic][1][1])
    assert not app.exception
    next_button = app.button(key=f"lab_{topic}_next_explore")
    assert next_button.label == "Next: explore"
    assert next_button.proto.type == "primary"

    next_button.click().run()
    assert _step(app, topic) == 2
    assert _widget_keys(_columns(app, topic)[0]) == step_widgets(topic, 2)


# ---- Step 2: explore ------------------------------------------------------------

def test_the_comparison_table_belongs_to_step_two_of_the_limits_tab():
    for step in (1, 3):
        assert _lab(lab_limits_step=step).dataframe == []
    app = _lab(lab_limits_step=2)

    tab = list(app.tabs[0].children.values())
    heading = next(
        index for index, child in enumerate(tab)
        if child.type == "markdown" and child.value == "**Compare values from both sides**"
    )
    # Under both columns, straight on the page.
    assert tab[heading - 1].type == "flex_container"
    assert tab[heading + 1].type == "dataframe"
    assert len(tab[heading + 1].value) == 6
    app.select_slider(key="concept_lab_limit_distance").set_value(0.001).run()
    assert float(app.metric[0].value) == pytest.approx(3.999)
    assert float(app.metric[1].value) == pytest.approx(4.001)


def test_explore_controls_keep_their_keys_and_drive_the_chart():
    app = _lab(lab_derivatives_step=2, lab_corner_step=2)
    app.slider(key="concept_lab_x0").set_value(2.0).run()
    app.select_slider(key="concept_lab_h").set_value(0.001).run()
    assert float(app.metric[3].value) == 7.0
    assert abs(float(app.metric[2].value) - 7.0) < 0.01
    app.button(key="lab_save_secant").click().run()
    assert app.session_state["lab_saved_secant"]["x0"] == 2.0
    assert any(item.value.startswith("Saved comparison: ") for item in app.caption)
    app.button(key="lab_corner_approach").click().run()
    assert app.select_slider(key="concept_lab_corner_h").value == 0.1
    assert not app.exception


@pytest.mark.parametrize("topic", TOPICS)
def test_reset_experiment_restarts_the_tab_at_step_one(topic):
    app = _lab()
    _check(app, topic, PREDICTIONS[topic][1][0])
    app.button(key=f"lab_{topic}_next_explore").click().run()
    app.button(key=f"lab_{topic}_reset").click().run()

    assert not app.exception
    assert _step(app, topic) == 1
    assert app.radio(key=f"lab_{topic}_prediction").value is None
    assert f"lab_{topic}_checked" not in app.session_state


# ---- Moving between steps keeps what the student did ----------------------------

def test_back_and_next_keep_the_prediction_the_sliders_and_the_typed_text():
    app = _lab()
    _check(app, "derivatives", "Always zero")
    app.button(key="lab_derivatives_next_explore").click().run()
    app.slider(key="concept_lab_x0").set_value(2.0).run()
    app.select_slider(key="concept_lab_h").set_value(0.01).run()
    app.radio(key="concept_lab_side").set_value("Left").run()
    app.toggle(key="concept_lab_zoom").set_value(False).run()
    app.button(key="lab_derivatives_next_explain").click().run()
    app.text_area(key="lab_derivatives_explanation").input("Shrinking h makes the secant turn.").run()

    # Step 3 still draws the chart from the slider values.
    assert float(app.metric[3].value) == 7.0
    app.button(key="lab_derivatives_back_to_2").click().run()
    assert not app.exception
    assert app.slider(key="concept_lab_x0").value == 2.0
    assert app.select_slider(key="concept_lab_h").value == 0.01
    assert app.radio(key="concept_lab_side").value == "Left"
    assert app.toggle(key="concept_lab_zoom").value is False

    app.button(key="lab_derivatives_back_to_1").click().run()
    assert app.radio(key="lab_derivatives_prediction").value == "Always zero"
    assert any("horizontal line" in item.value for item in app.info)
    assert "Choose a prediction first." not in [item.value for item in app.info]

    app.button(key="lab_derivatives_next_explore").click().run()
    assert app.slider(key="concept_lab_x0").value == 2.0
    app.button(key="lab_derivatives_next_explain").click().run()
    assert app.text_area(key="lab_derivatives_explanation").value == "Shrinking h makes the secant turn."
    assert not app.exception
    assert not any("Session State API" in item.value for item in app.warning)


# ---- Step 3: explain -------------------------------------------------------------

@pytest.mark.parametrize("topic", TOPICS)
@pytest.mark.parametrize("right", [True, False])
def test_the_answer_waits_for_show_answer_then_says_how_the_prediction_went(topic, right):
    choices = PREDICTIONS[topic][1]
    picked = choices[0] if right else choices[2]
    app = _lab()
    _check(app, topic, picked)
    app.button(key=f"lab_{topic}_next_explore").click().run()
    app.button(key=f"lab_{topic}_next_explain").click().run()

    question = EXPLANATIONS[topic][0]
    block = _explain_block(app, topic)
    assert [node.value for node in _walk(block) if node.type == "subheader"][0] == question
    assert app.text_area(key=f"lab_{topic}_explanation").label == "Your explanation"
    assert any("Only you see this. Write it first, then compare." in m.value and 'role="tooltip"' in m.value for m in app.markdown)
    show = app.button(key=f"lab_{topic}_show_answer")
    assert show.label == "Show answer"
    assert not _answer_on_page(app, topic)
    assert not any(button.key == f"lab_{topic}_self_right" for button in app.button)

    show.click().run()
    assert not app.exception
    assert app.button(key=f"lab_{topic}_show_answer").label == "Hide answer"
    assert _answer_on_page(app, topic)
    content = [node for node in _walk(_explain_block(app, topic)) if not isinstance(node, Block)]
    types = [node.type for node in content]
    # The answer comes right after the button.
    after = types[types.index("button") + 1:]
    _, formula, answer = EXPLANATIONS[topic]
    expected = (["latex"] if formula else []) + ["markdown", "success" if right else "info"]
    assert after[:len(expected)] == expected
    outcome = content[types.index("button") + len(expected)].value
    if right:
        assert outcome == "Your prediction was right."
    else:
        assert outcome == f"Your prediction was “{picked}”; the experiment shows “{choices[0]}”."

    assert [app.button(key=f"lab_{topic}_self_{choice}").label for choice in ("right", "missed")] == [
        "I had it right", "I missed something",
    ]
    app.button(key=f"lab_{topic}_self_missed").click().run()
    assert app.button(key=f"lab_{topic}_self_missed").proto.type == "primary"
    assert app.session_state[f"lab_{topic}_self_check"] == "missed"

    app.button(key=f"lab_{topic}_show_answer").click().run()
    assert not _answer_on_page(app, topic)
    assert app.button(key=f"lab_{topic}_show_answer").label == "Show answer"


def test_show_answer_is_a_small_left_button_and_the_state_is_per_tab():
    app = _lab(lab_limits_step=3, lab_corner_step=3, lab_limits_checked="4")
    app.button(key="lab_limits_show_answer").click().run()

    assert _answer_on_page(app, "limits") and not _answer_on_page(app, "corner")
    button = app.button(key="lab_limits_show_answer")
    assert button.proto.type == "secondary"
    # Moving a slider on another tab keeps the answer open.
    app.session_state["lab_derivatives_step"] = 2
    app.run()
    app.slider(key="concept_lab_x0").set_value(-1.0).run()
    assert _answer_on_page(app, "limits")
    assert app.session_state["lab_limits_answer_shown"] is True


@pytest.mark.parametrize("topic", TOPICS)
def test_start_again_resets_the_tab_and_returns_to_step_one(topic):
    app = _lab()
    _check(app, topic, PREDICTIONS[topic][1][1])
    app.button(key=f"lab_{topic}_next_explore").click().run()
    if topic == "derivatives":
        app.slider(key="concept_lab_x0").set_value(2.0).run()
        app.button(key="lab_save_secant").click().run()
    app.button(key=f"lab_{topic}_next_explain").click().run()
    app.text_area(key=f"lab_{topic}_explanation").input("My idea").run()
    app.button(key=f"lab_{topic}_show_answer").click().run()
    app.button(key=f"lab_{topic}_self_right").click().run()

    app.button(key=f"lab_{topic}_start_again").click().run()

    assert not app.exception
    assert _step(app, topic) == 1
    assert app.radio(key=f"lab_{topic}_prediction").value is None
    for key in (f"lab_{topic}_checked", f"lab_{topic}_answer_shown", f"lab_{topic}_self_check",
                f"lab_{topic}_explanation", "lab_saved_secant" if topic == "derivatives" else f"lab_{topic}_checked"):
        assert key not in app.session_state, key
    assert app.session_state["concept_lab_x0"] == 1.0
    _check(app, topic, PREDICTIONS[topic][1][0])
    app.button(key=f"lab_{topic}_next_explore").click().run()
    app.button(key=f"lab_{topic}_next_explain").click().run()
    assert app.text_area(key=f"lab_{topic}_explanation").value == ""
    assert not _answer_on_page(app, topic)


# ---- Across tabs and pages ------------------------------------------------------

def test_each_tab_keeps_its_step_across_reruns_and_a_page_visit():
    from services.learning_flow import open_lab

    app = signed_in_app(ROOT / "app.py").run()
    open_lab(app.session_state, "calculus-i-demo", "calc_derivatives")
    app.switch_page("pages/6_Concept_Lab.py").run()
    assert not app.exception
    # The requested topic still opens its tab.
    assert app.get("tab_container")[0].proto.tab_container.default_tab_index == 1

    _check(app, "limits", "4")
    app.button(key="lab_limits_next_explore").click().run()
    _check(app, "derivatives", "The tangent slope at x₀")
    app.button(key="lab_derivatives_next_explore").click().run()
    app.slider(key="concept_lab_x0").set_value(2.0).run()
    app.button(key="lab_derivatives_next_explain").click().run()
    app.select_slider(key="concept_lab_limit_distance").set_value(0.01).run()
    assert [_step(app, topic) for topic in TOPICS] == [2, 3, 1]

    app.switch_page("pages/4_Knowledge_Graph.py").run()
    assert not app.exception and app.title[0].value == "Knowledge Map"
    app.switch_page("pages/6_Concept_Lab.py").run()

    assert not app.exception
    assert [_step(app, topic) for topic in TOPICS] == [2, 3, 1]
    assert app.get("tab_container")[0].proto.tab_container.default_tab_index == 1
    for topic, step in zip(TOPICS, (2, 3, 1)):
        assert _widget_keys(_columns(app, topic)[0]) == step_widgets(topic, step, checked=False)
    # What the student set is kept, on screen or not when they left.
    assert app.select_slider(key="concept_lab_limit_distance").value == 0.01
    assert app.session_state["concept_lab_x0"] == 2.0
    assert app.session_state["lab_derivatives_prediction"] == "The tangent slope at x₀"
    assert float(app.metric[3].value) == 7.0
    assert float(app.metric[0].value) == pytest.approx(3.99)
    assert not any("Session State API" in item.value for item in app.warning)


# ---- Chinese ---------------------------------------------------------------------

MATH = re.compile(r"\\[a-z]+|[a-z]\(|\b[a-z]\b|x₀|f′")


def _english_words(texts: list[str]) -> list[str]:
    words = []
    for text in texts:
        text = re.sub(r"<[^>]+>", " ", text)
        text = MATH.sub(" ", text)
        words += re.findall(r"[A-Za-z]{2,}", text)
    return words


@pytest.mark.parametrize("topic", TOPICS)
def test_every_step_is_chinese_with_the_chinese_interface(topic):
    wrong = PREDICTIONS[topic][1][1]
    app = _lab(chinese=True)
    _check(app, topic, wrong)
    texts = _texts(app.tabs[TAB[topic]])
    app.button(key=f"lab_{topic}_next_explore").click().run()
    texts += _texts(app.tabs[TAB[topic]])
    app.button(key=f"lab_{topic}_next_explain").click().run()
    app.button(key=f"lab_{topic}_show_answer").click().run()
    app.button(key=f"lab_{topic}_self_right").click().run()
    texts += _texts(app.tabs[TAB[topic]])

    assert not app.exception
    joined = "\n".join(texts)
    for chinese in ("预测", "探索", "解释", "下一步：探索", "下一步：解释", "返回", "你的解释",
                    "只有你能看到。先写下来，再对照答案。", "收起答案", "我答对了", "我漏掉了一些",
                    "重新开始", "你的预测是“"):
        assert chinese in joined, chinese
    assert _english_words(texts) == []


# ---- Styles ----------------------------------------------------------------------

def test_step_indicator_marks_the_current_step_with_paper_tokens():
    css = (ROOT / "assets" / "paper_panels.css").read_text(encoding="utf-8")
    steps = '[data-testid="stMain"] [data-testid="stMarkdownContainer"] ol.lab-steps'

    def rule(selector: str) -> str:
        match = re.search(re.escape(selector) + r" \{\n(.*?)\n\}", css, re.DOTALL)
        assert match, selector
        return match.group(1)

    assert "display: flex;" in rule(steps) and "flex-wrap: wrap;" in rule(steps)
    current = rule(f"{steps} li.lab-step.is-current")
    assert "var(--paper-select)" in current and "var(--accent-rust-text)" in current
    assert "var(--paper-badge)" in rule(f"{steps} li.lab-step")
    # The list is not a paragraph, so its block keeps its gap to the step below.
    assert "margin-bottom: 0;" in rule(
        '[data-testid="stMain"] [data-testid="stMarkdownContainer"]:has(> ol.lab-steps)'
    )


# ---- A control that first appears in step 2 ---------------------------------------

STARTING_VALUES = {
    "limits": {"concept_lab_limit_distance": 0.1},
    "derivatives": {"concept_lab_x0": 1.0, "concept_lab_h": 0.5, "concept_lab_zoom": True},
    "corner": {"concept_lab_corner_h": 0.5},
}


def _control(app: AppTest, key: str):
    for kind in ("select_slider", "slider", "toggle"):
        for element in getattr(app, kind):
            if element.key == key:
                return element
    raise AssertionError(f"No control with key {key}")


@pytest.mark.parametrize("topic", TOPICS)
def test_controls_are_told_their_starting_value_when_step_two_first_appears(topic):
    # The browser shows a control's own default unless the run that first draws
    # it also sets its value. The starting values differ from those defaults
    # (0.1, not the first distance), and the chart already uses them in step 1.
    app = _lab()
    choice = PREDICTIONS[topic][1][0]
    app.radio(key=f"lab_{topic}_prediction").set_value(choice).run()
    app.button(key=f"lab_{topic}_check").click().run()
    app.button(key=f"lab_{topic}_next_explore").click().run()
    assert not app.exception
    for key, value in STARTING_VALUES[topic].items():
        control = _control(app, key)
        assert control.value == value
        assert control.proto.set_value, f"{key} would show its own default in the browser"

    # Still told on a later run, after another control changed.
    app.button(key=f"lab_{topic}_approach").click().run()
    for key in STARTING_VALUES[topic]:
        assert _control(app, key).proto.set_value


def test_corner_conclusion_waits_until_the_student_has_predicted():
    # The line answers the step-1 question, so step 1 must not show it.
    line = "The two slopes disagree: no derivative at 0."
    title = "Continuous does not always mean differentiable"
    first = _lab()
    assert line not in [info.value for info in first.info]
    # The tab's full title says the same thing, so step 1 shows a neutral one.
    assert title not in [s.value for s in first.subheader]
    assert "A corner at x = 0" in [s.value for s in first.subheader]
    for step in (2, 3):
        later = _lab(lab_corner_step=step)
        assert line in [info.value for info in later.info]
        assert title in [s.value for s in later.subheader]


@pytest.mark.parametrize("topic", TOPICS)
def test_a_double_click_on_show_answer_leaves_the_answer_shown(topic):
    # The button carries the state it asks for, so the same click arriving twice
    # (the second half of a double click landing after the rerun started) changes nothing.
    twice = AppTest.from_string(
        "import streamlit as st\n"
        "from services.concept_lab_ui import _set_answer_shown\n"
        f"_set_answer_shown({topic!r}, True)\n"
        f"_set_answer_shown({topic!r}, True)\n"
        f"st.write(str(st.session_state['lab_{topic}_answer_shown']))\n"
    ).run()
    assert not twice.exception and twice.markdown[0].value == "True"

    app = _lab(**{f"lab_{topic}_step": 3})
    assert app.button(key=f"lab_{topic}_show_answer").label == "Show answer"
    app.button(key=f"lab_{topic}_show_answer").click().run()
    assert app.session_state[f"lab_{topic}_answer_shown"] is True
    assert app.button(key=f"lab_{topic}_show_answer").label == "Hide answer"
    app.button(key=f"lab_{topic}_show_answer").click().run()
    assert app.session_state[f"lab_{topic}_answer_shown"] is False
    assert app.button(key=f"lab_{topic}_show_answer").label == "Show answer"


def test_practice_appears_only_after_self_check_and_before_the_navigation_row():
    app = _lab(lab_limits_step=3)
    assert not any(button.key == PRACTICE['limits'] for button in app.button)
    app.button(key='lab_limits_show_answer').click().run()
    assert not any(button.key == PRACTICE['limits'] for button in app.button)
    app.button(key='lab_limits_self_right').click().run()
    keys = [button.key for button in app.button]
    assert keys.index(PRACTICE['limits']) < keys.index('lab_limits_back_to_2') < keys.index('lab_limits_start_again')
    app.button(key='lab_limits_start_again').click().run()
    assert not any(button.key == PRACTICE['limits'] for button in app.button)
