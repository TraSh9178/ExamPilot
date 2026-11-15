"""Answers behind Learning DNA (pages/12_Learning_Evidence.py), opened from Progress.

Also covers the two cleanups that came with it: the review list on Progress is
drawn by render_priorities again, and the practice result shows its time by
topic as bars.
"""
from tests.tooltip_helpers import supporting_texts, tooltip_texts

import ast
import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import ExamSession, StudyPackage
from services.exam_engine import grade_exam
from services.i18n import LANGUAGE_KEY, _DYNAMIC, _TRANSLATIONS
from services.practice_insights import analytics, session_insights, set_session_insights
from tests.test_anki_export_page import _keyed_blocks, _top_level_order
from tests.test_progress_charts import (
    COURSE_ID,
    LATIN,
    TOPIC_NAMES,
    aria_label,
    bar_rows,
    chart_course_and_history,
    charts,
    course_strings,
    interface_strings,
    progress_app,
    visible_text,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "pages" / "12_Learning_Evidence.py"
EVIDENCE_PAGE = "pages/12_Learning_Evidence.py"
PROGRESS_PAGE = "pages/3_Performance.py"
TOPIC_KEY = f"learning_evidence_topic_{COURSE_ID}"
COLUMNS = ["Dimension", "Question", "Latest answer", "In-app hints shown", "Confidence"]
NONE = "Not recorded"

# Read from the per-topic "View evidence" expanders on Progress at 113a0be for
# prepared() below: (topic, rows) in course order, one row per latest answer.
EXPANDERS_AT_113A0BE = {
    "mock": [
        ("Rates & <Ratios>", [
            ("Computation", "Question r0?", "Correct", NONE, NONE),
            ("Computation", "Question r2?", "Correct", NONE, NONE),
            ("Computation", "Question r4?", "Correct", NONE, NONE),
            ("Conceptual understanding", "Question r1?", "Correct", NONE, "Unsure"),
            ("Conceptual understanding", "Question r3?", "Correct", NONE, NONE),
        ]),
        ("Limits", [
            ("Computation", "Question l1?", "Correct", NONE, NONE),
            ("Conceptual understanding", "Question l0?", "Incorrect", NONE, NONE),
            ("Conceptual understanding", "Question l2?", "Incorrect", NONE, NONE),
        ]),
        ("Series", [
            ("Computation", "Question s0?", "Correct", NONE, NONE),
        ]),
    ],
    "topic": [
        ("Rates & <Ratios>", [
            ("Computation", "Question r0?", "Incorrect", "2", "Sure"),
            ("Computation", "Question r2?", "Correct", NONE, NONE),
            ("Computation", "Question r4?", "Correct", NONE, NONE),
            ("Conceptual understanding", "Question r1?", "Correct", "0", "Guessed"),
        ]),
        ("Limits", [
            ("Computation", "Question l1?", "Correct", NONE, NONE),
            ("Computation", "Question l3?", "Incorrect", NONE, NONE),
            ("Conceptual understanding", "Question l0?", "Correct", NONE, NONE),
            ("Conceptual understanding", "Question l2?", "Correct", NONE, NONE),
        ]),
    ],
}
MODE_LABELS = {"mock": "Mock Exam", "topic": "Topic Practice"}


def prepared():
    """The chart fixture with confidence and hint counts recorded for some answers."""
    course, history = chart_course_and_history()
    course = set_session_insights(course, "t1", {
        "r0": {"confidence": "sure", "hints_used": 2, "focus_seconds": 61.0},
        "r1": {"confidence": "guessed", "hints_used": 0, "focus_seconds": 40.0},
    })
    course = set_session_insights(course, "m2", {"r1": {"confidence": "unsure", "focus_seconds": 15.0},
                                                 "s0": {"focus_seconds": 95.0}})
    return course, history


def evidence_app(course=None, history=None, *, mode=None, topic=None, chinese=False):
    app = AppTest.from_file(str(EVIDENCE_PATH), default_timeout=30)
    if course is not None:
        app.session_state["current_course"] = course
        if history is not None:
            app.session_state[f"practice_history_{course.course_id}"] = history
        if mode is not None:
            app.session_state[f"performance_mode_{course.course_id}"] = mode
        if topic is not None:
            app.session_state[f"learning_evidence_topic_{course.course_id}"] = topic
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run()


def tables(app):
    """(heading, rows) for each topic on the evidence page, top to bottom."""
    found = []
    for key, block in _keyed_blocks(app.main):
        if key.startswith("learning_evidence_") and key != "learning_evidence_back":
            heading = [item.value for item in block.subheader]
            frames = [item.value for item in block.dataframe]
            assert len(heading) == 1 and len(frames) == 1, key
            frame = frames[0]
            found.append((heading[0], list(frame.columns),
                          [tuple(str(value) for value in row) for row in frame.itertuples(index=False)]))
    return found


def answer_buttons(app):
    return [button for button in app.button if (button.key or "").startswith("learning_evidence_open_")]


def edge(app, key):
    holder = dict(_keyed_blocks(app.main))[f"page_link_{key}"].proto.flex_container
    assert holder.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
    return {
        BlockProto.FlexContainer.Justify.JUSTIFY_START: "left",
        BlockProto.FlexContainer.Justify.JUSTIFY_END: "right",
    }.get(holder.justify, "middle")


def all_blocks(node):
    for child in node.children.values():
        if isinstance(child, Block):
            yield child
            yield from all_blocks(child)


# ---- Progress: a small button per topic instead of the expander ---------------------------


@pytest.mark.parametrize("state", ["real-mock", "real-topic", "example", "empty-demo", "empty-course"])
def test_progress_has_no_expander_in_any_state(state):
    from tests.test_example_report import demo

    if state.startswith("real"):
        course, history = prepared()
        app = progress_app(course, history, mode=MODE_LABELS[state.split("-")[1]])
    elif state == "example":
        app = progress_app(demo("calculus_i_demo.json"))
    elif state == "empty-demo":
        course = demo("sample_course.json")
        course.learning_state["session_order"] = ["saved-elsewhere"]
        app = progress_app(course)
    else:
        course, _ = chart_course_and_history()
        course.learning_state.clear()
        app = progress_app(course)
    assert not app.exception
    assert not app.expander
    assert not any(block.type == "expander" for block in all_blocks(app.main))
    if not state.startswith("real"):
        # The example report and an empty history have no answers to open.
        assert not answer_buttons(app)


@pytest.mark.parametrize("mode", ["mock", "topic"])
def test_each_topic_with_answers_has_one_small_right_edge_button(mode):
    course, history = prepared()
    app = progress_app(course, history, mode=MODE_LABELS[mode])
    assert not app.exception
    with_answers = {name for name, _ in EXPANDERS_AT_113A0BE[mode]}
    buttons = answer_buttons(app)
    assert [b.key for b in buttons] == [
        f"learning_evidence_open_{topic_id}" for topic_id, name in TOPIC_NAMES.items() if name in with_answers
    ]
    assert all(b.label == "View answers" for b in buttons)
    for button in buttons:
        assert edge(app, button.key) == "right"
        # Inside its topic's Learning DNA card, under the bars.
        topic_id = button.key.removeprefix("learning_evidence_open_")
        card = dict(_keyed_blocks(app.main))[f"learning_dna_{topic_id}"]
        assert [b.key for b in card.button] == [button.key]
    # Series has no answers in topic practice, so no button there.
    assert ("learning_evidence_open_series" in [b.key for b in buttons]) == (mode == "mock")


def test_button_remembers_the_topic_and_opens_the_evidence_page(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    course, history = prepared()
    app = progress_app(course, history, mode="Topic Practice")
    app.button(key="learning_evidence_open_limits").click().run()
    assert not app.exception
    assert destinations == [EVIDENCE_PAGE]
    assert app.session_state[TOPIC_KEY] == "limits"


def test_registered_app_opens_the_answers_with_the_mode_and_topic_and_comes_back():
    from tests.auth_helpers import signed_in_app

    course, history = prepared()
    app = signed_in_app(ROOT / "app.py").run()
    app.session_state["current_course"] = course
    app.session_state[f"practice_history_{COURSE_ID}"] = history
    app.switch_page(PROGRESS_PAGE).run()
    app.radio(key=f"performance_mode_{COURSE_ID}").set_value("Topic Practice").run()
    assert not app.exception and app.title[0].value == "Progress"

    app.button(key="learning_evidence_open_limits").click().run()
    assert not app.exception
    assert app.title[0].value == "Answers behind Learning DNA"
    # The mode chosen on Progress carries over, and the clicked topic comes first.
    assert app.radio(key=f"performance_mode_{COURSE_ID}").value == "Topic Practice"
    assert [heading for heading, _, _ in tables(app)] == ["Limits", "Rates & <Ratios>"]

    # AppTest reruns the page it last switched to, so the way back is clicked
    # after switching to the page directly.
    app.switch_page(EVIDENCE_PAGE).run()
    assert app.radio(key=f"performance_mode_{COURSE_ID}").value == "Topic Practice"
    app.button(key="learning_evidence_back").click().run()
    assert not app.exception
    assert app.title[0].value == "Progress"
    # The way back keeps the mode too: Progress does not fall back to Mock Exam.
    assert app.radio(key=f"performance_mode_{COURSE_ID}").value == "Topic Practice"


def test_registered_app_opens_another_topic_and_the_mode_can_change_there():
    from tests.auth_helpers import signed_in_app

    course, history = prepared()
    app = signed_in_app(ROOT / "app.py").run()
    app.session_state["current_course"] = course
    app.session_state[f"practice_history_{COURSE_ID}"] = history
    app.switch_page(PROGRESS_PAGE).run()
    app.button(key="learning_evidence_open_series").click().run()
    assert app.title[0].value == "Answers behind Learning DNA"
    assert app.radio(key=f"performance_mode_{COURSE_ID}").value == "Mock Exam"
    assert [heading for heading, _, _ in tables(app)] == ["Series", "Rates & <Ratios>", "Limits"]
    app.switch_page(EVIDENCE_PAGE).run()
    app.radio(key=f"performance_mode_{COURSE_ID}").set_value("Topic Practice").run()
    assert not app.exception
    assert [heading for heading, _, _ in tables(app)] == ["Rates & <Ratios>", "Limits"]


def test_app_registers_the_page_as_a_hidden_focus_page(monkeypatch):
    from tests.test_paper_shell import sidebar_navigation

    visible, hidden, _ = sidebar_navigation(monkeypatch)
    page = next(page for page in hidden if page.url_path == "Learning_Evidence")
    assert page.title == "Answers behind Learning DNA"
    assert Path(page._page).resolve() == EVIDENCE_PATH.resolve()
    assert "Answers behind Learning DNA" not in [item.title for item in visible]


# ---- The evidence page --------------------------------------------------------------------


def test_page_has_back_button_title_caption_mode_and_tables_only(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    course, history = prepared()
    app = evidence_app(course, history, mode="Mock Exam")
    assert not app.exception

    order = [entry for entry in _top_level_order(app) if entry != "markdown"]
    assert order[:3] == ["page_link_learning_evidence_back", "title", "radio"]
    assert edge(app, "learning_evidence_back") == "left"
    back = app.button(key="learning_evidence_back")
    assert back.label == "Back to Progress" and back.proto.icon == ":material/arrow_back:"
    assert [item.value for item in app.title] == ["Answers behind Learning DNA"]
    from tests.tooltip_helpers import tooltip_texts
    assert tooltip_texts(app) == ["Your latest answer to each question behind your Learning DNA, topic by topic."]
    radio = app.radio(key=f"performance_mode_{COURSE_ID}")
    assert radio.label == "Performance mode" and list(radio.options) == ["Mock Exam", "Topic Practice"]
    assert radio.horizontal

    # Then one keyed block per topic with answers, and nothing else.
    assert order[3:] == [f"learning_evidence_{topic_id}" for topic_id in ("rates", "limits", "series")]
    assert [button.key for button in app.button] == ["learning_evidence_back"]
    assert not app.expander and not app.metric and not app.info and not app.warning
    assert [m.value for m in app.markdown if not m.value.startswith("<style") and "quiet-help-row" not in m.value] == []
    assert len(app.dataframe) == 3

    back.click().run()
    assert destinations == [PROGRESS_PAGE]


@pytest.mark.parametrize("mode", ["mock", "topic"])
def test_tables_match_what_the_expanders_showed(mode):
    course, history = prepared()
    app = evidence_app(course, history, mode=MODE_LABELS[mode])
    assert not app.exception
    assert tables(app) == [
        (name, COLUMNS, rows) for name, rows in EXPANDERS_AT_113A0BE[mode]
    ]


def test_the_requested_topic_comes_first_and_the_rest_keep_course_order():
    course, history = prepared()
    app = evidence_app(course, history, mode="Mock Exam", topic="series")
    assert [heading for heading, _, _ in tables(app)] == ["Series", "Rates & <Ratios>", "Limits"]
    app = evidence_app(course, history, mode="Mock Exam", topic="limits")
    assert [heading for heading, _, _ in tables(app)] == ["Limits", "Rates & <Ratios>", "Series"]
    # A topic with no answers in this mode (or an unknown one) changes nothing.
    for topic in ("series", "gone"):
        app = evidence_app(course, history, mode="Topic Practice", topic=topic)
        assert [heading for heading, _, _ in tables(app)] == ["Rates & <Ratios>", "Limits"]
    by_topic = dict((name, rows) for name, _, rows in tables(evidence_app(course, history, mode="Mock Exam",
                                                                              topic="series")))
    assert by_topic == {name: rows for name, rows in EXPANDERS_AT_113A0BE["mock"]}


def test_mode_choice_on_the_page_switches_the_tables():
    course, history = prepared()
    app = evidence_app(course, history, mode="Mock Exam")
    app.radio(key=f"performance_mode_{COURSE_ID}").set_value("Topic Practice").run()
    assert not app.exception
    assert [heading for heading, _, _ in tables(app)] == ["Rates & <Ratios>", "Limits"]


def test_page_without_a_course(monkeypatch):
    links = []
    monkeypatch.setattr(st, "page_link", lambda page, label=None, **kwargs: links.append((page, label)))
    app = evidence_app()
    assert not app.exception
    assert [item.value for item in app.info] == ["Load a course from the dashboard first."]
    assert links == [("pages/0_Dashboard.py", "Back to Dashboard")]
    assert app.button(key="learning_evidence_back").label == "Back to Progress"
    assert not app.radio and not app.dataframe


NO_ANSWERS = "No answers behind Learning DNA in this mode yet."


def test_page_with_no_history_shows_one_line():
    course, _ = chart_course_and_history()
    course.learning_state.clear()
    app = evidence_app(course)
    assert not app.exception
    assert [item.value for item in app.info] == [NO_ANSWERS]
    assert not app.dataframe and not app.subheader


def test_page_with_history_but_no_answers_in_this_mode():
    course, history = prepared()
    topic_only = {sid: record for sid, record in history.items() if record["session"].mode == "topic"}
    app = evidence_app(course, topic_only, mode="Mock Exam")
    assert not app.exception
    assert [item.value for item in app.info] == [NO_ANSWERS]
    assert not app.dataframe
    # Untagged questions give no answers either. History keeps its own copy of
    # each question, and that copy's tag is the one that counts.
    course, history = prepared()
    for question in [*course.questions, *(q for record in history.values() for q in record["questions"])]:
        question.cognitive_dimension = None
    app = evidence_app(course, history, mode="Topic Practice")
    assert [item.value for item in app.info] == [NO_ANSWERS] and not app.dataframe


def test_demo_course_without_practice_shows_no_example_answers():
    from tests.test_example_report import demo

    app = evidence_app(demo("demo_python_basics.json"))
    assert not app.exception
    assert [item.value for item in app.info] == [NO_ANSWERS]
    assert not app.dataframe
    assert "example" not in repr(app.session_state.filtered_state).lower()


def test_unreadable_history_shows_a_warning_not_an_error():
    course, history = prepared()
    history["m1"]["session"] = ExamSession(session_id="m1", mode="mock", question_ids=["r0"])
    app = evidence_app(course, history, mode="Mock Exam")
    assert not app.exception
    assert [item.value for item in app.warning] == ["Learning DNA couldn't read this practice history."]
    assert not app.dataframe


def _texts(app):
    texts = [item.value for kind in ("title", "subheader", "caption", "info", "warning") for item in app.get(kind)]
    texts += [visible_text(m.value) for m in app.markdown if not m.value.startswith("<style")]
    texts += [button.label for button in app.button]
    for radio in app.radio:
        texts += [radio.label, *radio.options]
    for frame in app.dataframe:
        texts += [str(column) for column in frame.value.columns]
        texts += [str(value) for value in frame.value.astype(object).values.ravel()]
    return texts


def _without_course_text(texts, course):
    content = sorted(course_strings(course), key=len, reverse=True)
    leftovers = []
    for text in texts:
        for piece in content:
            text = text.replace(piece, "")
        leftovers.append(text)
    return leftovers


def test_evidence_page_in_chinese_has_no_english():
    course, history = prepared()
    texts = []
    for mode in ("模拟考试", "知识点练习"):
        app = evidence_app(course, history, mode=mode, chinese=True)
        assert not app.exception
        texts += _texts(app)
    empty, _ = chart_course_and_history()
    empty.learning_state.clear()
    texts += _texts(evidence_app(empty, chinese=True))
    assert "返回学习进度" in texts and "学习画像的依据" in texts and "能力维度" in texts
    assert "此模式下还没有学习画像所依据的作答。" in texts
    assert [text for text in _without_course_text(texts, course) if LATIN.search(text)] == []


def test_progress_buttons_in_chinese():
    course, history = prepared()
    app = progress_app(course, history, mode="知识点练习", chinese=True)
    assert not app.exception
    assert [b.label for b in answer_buttons(app)] == ["查看作答", "查看作答"]
    assert [text for text in interface_strings(app, course_strings(course)) if LATIN.search(text)] == []


def test_new_interface_strings_have_chinese_entries():
    for relative in ("pages/12_Learning_Evidence.py", "services/learning_dna_ui.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        literal = [
            node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        ]
        assert literal
        missing = [text for text in literal if text not in _TRANSLATIONS
                   and not any(re.fullmatch(pattern, text) for pattern, _ in _DYNAMIC)]
        assert missing == [], relative
    assert _TRANSLATIONS["Back to Progress"] == "返回学习进度"
    assert _TRANSLATIONS["View answers"] == "查看作答"


# ---- Progress: the review list comes from render_priorities again ---------------------------


def test_history_insights_draw_the_review_list_through_render_priorities():
    tree = ast.parse((ROOT / "services" / "practice_insights_ui.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "render_history_insights")
    calls = [node.func for node in ast.walk(function) if isinstance(node, ast.Call)]
    names = {getattr(func, "id", None) or getattr(func, "attr", None) for func in calls}
    assert "render_priorities" in names
    # No table, button or redirect of its own.
    assert not names & {"dataframe", "button", "switch_page", "launch_priority"}


def test_review_list_on_progress_is_unchanged():
    course, history = prepared()
    app = progress_app(course, history, mode="Topic Practice")
    assert not app.exception
    ranked = [frame.value for frame in app.dataframe if "Why review" in frame.value.columns]
    assert len(ranked) == 1 and list(ranked[0].columns) == ["Rank", "Topic", "Question", "Why review"]
    assert list(ranked[0]["Rank"]) == list(range(1, len(ranked[0]) + 1))
    assert any(text.startswith("Priority uses incorrect/unanswered responses") for text in tooltip_texts(app))
    assert "**Smart review list**" in [m.value for m in app.markdown]
    assert app.button(key=f"priorities_{COURSE_ID}").label == "Practise review priorities"
    # Starting practice from it is covered in tests/test_progress_charts.py.


# ---- Practice result: time by topic as bars -----------------------------------------------


def result_app(focus, chinese=False):
    from tests.test_practice_insights import PAGE, setup_course

    course = setup_course()
    picked = [course.questions[0], course.questions[1], course.questions[3]]
    session = ExamSession(session_id="s", mode="topic", question_ids=[q.id for q in picked])
    result = grade_exam(session, picked, {"q0": 0, "q1": 1, "q3": 0})
    course = set_session_insights(course, "s", {qid: {"focus_seconds": seconds} for qid, seconds in focus.items()})
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["current_course"] = course
    app.session_state["confirmed_scope_insights"] = ["t"]
    app.session_state["active_practice_insights"] = {
        "session": session, "questions": picked, "warning": None, "settings": {}, "result": result,
    }
    app.session_state["practice_history_insights"] = {
        "s": {"session": session, "questions": picked, "attempts": result["attempts"], "result": result},
    }
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run(), course, picked, result


@pytest.mark.parametrize("focus", [
    {"q0": 42.25, "q1": 20.0, "q3": 75.04},
    {"q0": 30.0, "q3": 12.5},
    {"q3": 5.0},
])
def test_result_time_bars_have_the_numbers_and_order_the_table_had(focus):
    app, course, picked, result = result_app(focus)
    assert not app.exception
    data = analytics(picked, result["attempts"], session_insights(course, "s"))
    names = {topic.id: topic.name for topic in course.topics}
    # What the dataframe showed: topic and seconds rounded to 0.1, longest first.
    table = [(names.get(t, "Topic"), round(seconds, 1))
             for t, seconds in sorted(data["topic_seconds"].items(), key=lambda p: -p[1])]
    found = charts(app, "time")
    assert len(found) == 1
    rows = bar_rows(found[0])
    assert [(row["label"], float(row["value"].removesuffix(" s"))) for row in rows] == table
    assert rows[0]["fill"] == 100.0
    assert aria_label(found[0]).startswith("Tracked focus time by topic: ")
    assert not any("Tracked seconds" in frame.value.columns for frame in app.dataframe)
    # The heading and the longest-question line stay.
    assert "**Tracked focus time by topic**" in [m.value for m in app.markdown]
    slowest = max(picked, key=lambda q: focus.get(q.id, 0))
    assert "Longest tracked question: " + slowest.question in [c.value for c in app.caption]


def test_result_without_tracked_time_shows_no_bars():
    app, *_ = result_app({})
    assert not app.exception
    assert not charts(app, "time")
    assert "**Tracked focus time by topic**" not in [m.value for m in app.markdown]


def test_result_time_bars_in_chinese():
    app, course, *_ = result_app({"q0": 42.25, "q3": 75.0}, chinese=True)
    assert not app.exception
    markup = charts(app, "time")[0]
    assert [row["value"] for row in bar_rows(markup)] == ["75 秒", "42.2 秒"]
    for text in _without_course_text([visible_text(markup), aria_label(markup)], course):
        assert not LATIN.search(text), text
    heading = _TRANSLATIONS["**Tracked focus time by topic**"]
    assert heading in [m.value for m in app.markdown]
    # The chart is named for screen readers with the same words as the heading.
    assert aria_label(markup).startswith(heading.strip("*") + ": ")
    assert any(c.value.startswith("记录时间最长的题目：") for c in app.caption)
