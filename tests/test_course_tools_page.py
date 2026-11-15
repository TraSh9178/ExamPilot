"""Study Plan opens Topic summaries and Course tools as pages of their own.

The Study Plan page keeps two small edge buttons instead of the expanders;
the Course tools page shows one tool at a time, chosen with one click.
"""
import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.runtime.state.common import user_key_from_element_id
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import Question, StudyPackage
from services.i18n import LANGUAGE_KEY
from services.question_editor import available_questions, status_for
from tests.auth_helpers import signed_in_app

ROOT = Path(__file__).resolve().parents[1]
STUDY_PLAN_PATH = ROOT / "pages" / "1_Study_Hub.py"
COURSE_TOOLS_PATH = ROOT / "pages" / "9_Course_Tools.py"
TOPIC_SUMMARIES_PATH = ROOT / "pages" / "10_Topic_Summaries.py"
STUDY_PLAN_PAGE = "pages/1_Study_Hub.py"
COURSE_TOOLS_PAGE = "pages/9_Course_Tools.py"
TOPIC_SUMMARIES_PAGE = "pages/10_Topic_Summaries.py"

TOOL_LABELS = ["Review and edit questions", "Account backup and recovery", "Source material"]
OLD_EXPANDERS = {
    "Topic summaries", "Course tools", *TOOL_LABELS,
    "Read saved text", "Question classification (advanced)",
}


# ---- Helpers ---------------------------------------------------------------

def choice_key(course) -> str:
    return f"course_tools_choice_{course.course_id}"


def course_tools_page(course, tool=None, *, chinese=False, signed_in=False, document=None) -> AppTest:
    """The Course tools page for `course`, set up but not run yet.

    `tool` is the internal name of the choice: "review", "backup" or "source";
    `document` is the saved course material, if any.
    """
    app = signed_in_app(COURSE_TOOLS_PATH) if signed_in else AppTest.from_file(str(COURSE_TOOLS_PATH))
    app.session_state["current_course"] = course
    if tool is not None:
        app.session_state[choice_key(course)] = tool
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    if document is not None:
        app.session_state[f"course_document_{course.course_id}"] = document
    return app


def make_course(reviews=None, questions=True) -> StudyPackage:
    return StudyPackage(
        course_id="c1",
        course_name="Course",
        topics=[
            {"id": "t1", "name": "Limits", "summary": "Limits summary.", "source_pages": [2, 3]},
            {"id": "t2", "name": "Series", "summary": "Series summary."},
            {"id": "t3", "name": "Derivatives", "summary": "Derivatives summary."},
        ],
        relationships=[],
        questions=[
            Question(
                id=f"q{index}", topic_id="t1", question=f"Question {index}?",
                options=["a", "b", "c", "d"], correct_index=1, explanation="Because.",
            )
            for index in range(1, 5)
        ] if questions else [],
        learning_state={"question_reviews": dict(reviews or {})},
    )


def make_chinese_course() -> StudyPackage:
    """Course content without Latin letters, so any English left is interface text."""
    return StudyPackage(
        course_id="c1",
        course_name="测试课程",
        topics=[
            {"id": "t1", "name": "极限", "summary": "极限的定义。", "source_pages": [2, 3]},
            {"id": "t2", "name": "级数", "summary": "级数的收敛。"},
        ],
        relationships=[],
        questions=[
            Question(
                id=f"q{index}", topic_id="t1", question=f"第{index}题是什么？",
                options=["一", "二", "三", "四"], correct_index=1, explanation="因为如此。",
            )
            for index in range(1, 4)
        ],
        learning_state={"question_reviews": {"q1": "pending", "q2": "approved", "q3": "flagged"}},
    )


def material(filename="lecture.pdf"):
    document = {"ok": True, "text": "Real source.", "pages": [{"page": 1, "text": "Real source."}]}
    if filename is not None:
        document["filename"] = filename
    return document


def study_plan(course, *, chinese=False) -> AppTest:
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = ["t1"]
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run()


def block_key(node):
    proto = getattr(node, "proto", None)
    if isinstance(node, Block) and isinstance(proto, BlockProto) and proto.id:
        return user_key_from_element_id(proto.id)
    return None


def edge_of(app, button_key) -> str:
    """Which edge the small page button with this key sits on."""
    holder = next(node for node in app.main if block_key(node) == f"page_link_{button_key}")
    flex = holder.proto.flex_container
    assert flex.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
    return {
        BlockProto.FlexContainer.Justify.JUSTIFY_START: "left",
        BlockProto.FlexContainer.Justify.JUSTIFY_END: "right",
    }.get(flex.justify, "middle")


def page_markdown(app):
    """Markdown on the page, without the stylesheet the app injects as markdown."""
    return [item.value for item in app.markdown if not item.value.lstrip().startswith("<style")]


def tool_markers(app, course) -> set[str]:
    """Which of the three tools is on screen, judged by their own widgets."""
    main = app.main
    shown = set()
    keys = {box.key for box in main.selectbox}
    if f"editor_question_{course.course_id}" in keys or "No questions available for review." in [
        item.value for item in main.caption
    ]:
        shown.add("review")
    if any((button.key or "").startswith("database_") for button in main.button):
        shown.add("backup")
    if main.checkbox or any("saved material" in item.value.lower() for item in main.caption):
        shown.add("source")
    return shown


def visible_texts(app) -> list[str]:
    """Every piece of interface text in the page area, including tooltips."""
    main = app.main
    texts = [item.value for kind in ("title", "header", "subheader", "caption") for item in main.get(kind)]
    texts += page_markdown(main)
    texts += [item.value for kind in ("info", "error", "warning", "success") for item in main.get(kind)]
    texts += [item.label for item in main.expander]
    for kind in ("button", "checkbox", "text_input", "text_area", "radio", "selectbox", "button_group"):
        for item in main.get(kind):
            texts += [item.label, item.proto.help]
            if kind in ("radio", "selectbox", "button_group"):
                texts += list(item.options)
    return [text for text in texts if text]


# The structure-label tooltip names two example labels; they are values a
# reviewer types, not interface words, and stay as they are in Chinese too.
EXAMPLE_LABELS = ("tangent_equation", "derivative_at_point")


def english_words(texts) -> list[str]:
    found = []
    for text in texts:
        for example in EXAMPLE_LABELS:
            text = text.replace(example, "")
        if re.search(r"[A-Za-z]{2,}", text):
            found.append(text)
    return found


def pin_chinese(monkeypatch):
    """Keep tr() in Chinese for the whole test, not only inside script runs.

    AppTest calls the question picker's format_func outside the script run,
    where the language setting is not visible, so a rerun would otherwise look
    for the English label of the selected question.
    """
    from types import SimpleNamespace

    from services import i18n

    monkeypatch.setattr(i18n, "st", SimpleNamespace(session_state={LANGUAGE_KEY: True}))


# ---- Study Plan: two small buttons instead of the expanders ----------------------

def test_study_plan_has_edge_buttons_instead_of_the_expanders():
    course = make_course({"q1": "pending"})
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.session_state["confirmed_scope_c1"] = ["t1"]
    app.session_state["course_document_c1"] = material()
    app.run()

    assert not app.exception
    assert not OLD_EXPANDERS & {item.label for item in app.expander}
    # None of the tools' content is left on the page.
    assert not any((box.key or "").startswith("editor_question_") for box in app.selectbox)
    assert not app.checkbox and not app.text_area and not app.text_input
    labels = [button.label for button in app.button]
    assert not {"Save review", "Save", "Restore", "Delete saved material"} & set(labels)
    assert "Manage questions, account backups and source material when needed." not in [
        item.value for item in app.caption
    ]
    assert not any("summary." in text for text in page_markdown(app))
    # One small button on each edge.
    assert labels.count("Topic summaries") == 1 and labels.count("Course tools") == 1
    assert edge_of(app, "open_topic_summaries") == "left"
    assert edge_of(app, "open_course_tools") == "right"
    assert app.button(key="open_topic_summaries").proto.icon == ":material/menu_book:"
    assert app.button(key="open_course_tools").proto.icon == ":material/build:"


def test_study_plan_buttons_switch_to_their_pages(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    app = study_plan(make_course())

    app.button(key="open_topic_summaries").click().run()
    app.button(key="open_course_tools").click().run()

    assert not app.exception
    assert destinations == [TOPIC_SUMMARIES_PAGE, COURSE_TOOLS_PAGE]


def test_topic_summaries_button_sits_above_the_scope_and_course_tools_at_the_bottom():
    app = study_plan(make_course({"q1": "approved"}))

    assert not app.exception
    top_level = list(app.main.children.values())
    keys = [block_key(node) for node in top_level]
    summaries = keys.index("page_link_open_topic_summaries")
    scope = keys.index("study_scope_panel")
    tools = keys.index("page_link_open_course_tools")
    assert summaries < scope < tools == len(top_level) - 1


def test_course_without_topics_offers_no_topic_summaries_button():
    course = make_course()
    course.topics = []
    course.questions = []
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.run()

    assert not app.exception
    assert "This course has no topics yet." in [item.value for item in app.info]
    labels = [button.label for button in app.button]
    assert "Topic summaries" not in labels and "Course tools" in labels


def test_pending_questions_point_to_course_tools():
    course = make_course({f"q{index}": "pending" for index in range(1, 5)})
    app = study_plan(course)

    assert not app.exception
    assert "Review and approve your generated questions in Course tools before starting practice." in [
        item.value for item in app.info
    ]


def test_study_plan_buttons_are_translated():
    app = study_plan(make_course({f"q{index}": "pending" for index in range(1, 5)}), chinese=True)

    assert not app.exception
    assert app.button(key="open_topic_summaries").label == "知识点概要"
    assert app.button(key="open_course_tools").label == "课程工具"
    assert "开始练习前请在课程工具中检查并批准生成的题目。" in [item.value for item in app.info]


@pytest.mark.parametrize(
    ("button", "page", "title", "back"),
    [
        ("open_topic_summaries", TOPIC_SUMMARIES_PAGE, "Topic summaries", "topic_summaries_back"),
        ("open_course_tools", COURSE_TOOLS_PAGE, "Course tools", "course_tools_back"),
    ],
)
def test_registered_app_opens_each_page_and_comes_back(button, page, title, back):
    app = signed_in_app(ROOT / "app.py").run()
    app.session_state["current_course"] = make_course({"q1": "pending"})
    app.switch_page(STUDY_PLAN_PAGE).run()
    assert not app.exception
    assert app.title[0].value == "Study Plan"

    app.button(key=button).click().run()
    assert not app.exception
    assert app.title[0].value == title

    # AppTest reruns the page it last switched to, so the way back is clicked
    # after switching to the page directly.
    app.switch_page(page).run()
    assert app.title[0].value == title
    app.button(key=back).click().run()
    assert not app.exception
    assert app.title[0].value == "Study Plan"


def test_registered_course_tools_page_opens_on_the_review_tool_each_time():
    # AppTest reruns the page it last switched to, so pages are opened with
    # switch_page here; the buttons themselves are checked above.
    app = signed_in_app(ROOT / "app.py").run()
    app.session_state["current_course"] = make_course({"q1": "pending"})
    app.switch_page(COURSE_TOOLS_PAGE).run()
    app.button_group(key="course_tools_choice_c1").set_value("source").run()
    assert not app.exception
    assert tool_markers(app, make_course()) == {"source"}
    app.run()
    assert tool_markers(app, make_course()) == {"source"}

    app.switch_page(STUDY_PLAN_PAGE).run()
    app.switch_page(COURSE_TOOLS_PAGE).run()
    assert not app.exception
    assert app.button_group(key="course_tools_choice_c1").value == "review"
    assert tool_markers(app, make_course()) == {"review"}


# ---- Topic summaries page --------------------------------------------------

def test_topic_summaries_page_shows_every_topic_in_course_order_and_nothing_else(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    course = make_course()
    app = AppTest.from_file(str(TOPIC_SUMMARIES_PATH))
    app.session_state["current_course"] = course
    app.run()

    assert not app.exception
    assert [item.value for item in app.title] == ["Topic summaries"]
    assert [button.label for button in app.button] == ["Back to Study Plan"]
    assert edge_of(app, "topic_summaries_back") == "left"
    assert page_markdown(app) == [
        "**Limits**", "Limits summary.",
        "**Series**", "Series summary.",
        "**Derivatives**", "Derivatives summary.",
    ]
    assert [item.value for item in app.caption] == ["Source pages: 2, 3"]
    # One bordered card per topic, directly on the page.
    cards = [
        node for node in app.main
        if isinstance(node, Block) and isinstance(node.proto, BlockProto)
        and node.proto.flex_container.border
    ]
    assert len(cards) == len(course.topics)
    assert [card.markdown[0].value for card in cards] == ["**Limits**", "**Series**", "**Derivatives**"]
    assert not app.expander and not app.info and not app.subheader
    for kind in ("selectbox", "radio", "checkbox", "text_input", "text_area", "button_group"):
        assert not app.get(kind)

    app.button(key="topic_summaries_back").click().run()
    assert destinations == [STUDY_PLAN_PAGE]


def test_topic_summaries_page_without_course_or_topics(monkeypatch):
    links = []
    monkeypatch.setattr(st, "page_link", lambda page, label=None, **kwargs: links.append((page, label)))
    app = AppTest.from_file(str(TOPIC_SUMMARIES_PATH)).run()
    assert not app.exception
    assert [item.value for item in app.info] == ["Load a course from the dashboard to start studying."]
    assert links == [("pages/0_Dashboard.py", "Back to Dashboard")]

    course = make_course()
    course.topics = []
    app = AppTest.from_file(str(TOPIC_SUMMARIES_PATH))
    app.session_state["current_course"] = course
    app.run()
    assert not app.exception
    assert [item.value for item in app.info] == ["This course has no topics yet."]
    assert page_markdown(app) == []


def test_topic_summaries_page_in_chinese_has_no_english():
    app = AppTest.from_file(str(TOPIC_SUMMARIES_PATH))
    app.session_state["current_course"] = make_chinese_course()
    app.session_state[LANGUAGE_KEY] = True
    app.run()

    assert not app.exception
    assert app.title[0].value == "知识点概要"
    assert app.button(key="topic_summaries_back").label == "返回学习计划"
    assert [item.value for item in app.caption] == ["来源页：2, 3"]
    assert english_words(visible_texts(app)) == []


# ---- Course tools page: one tool at a time ------------------------------------------

def test_course_tools_page_has_back_button_title_caption_and_one_click_choice(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    course = make_course({"q1": "pending"})
    app = course_tools_page(course).run()

    assert not app.exception
    assert [item.value for item in app.title] == ["Course tools"]
    assert app.caption[0].value == "Manage questions, account backups and source material when needed."
    assert app.button(key="course_tools_back").label == "Back to Study Plan"
    assert edge_of(app, "course_tools_back") == "left"
    # One click per tool: a button group, not a dropdown and not tabs.
    choice = app.button_group(key=choice_key(course))
    assert choice.options == TOOL_LABELS
    assert choice.value == "review"
    assert not app.tabs
    assert not any(box.label == "Choose a tool" for box in app.selectbox)
    assert tool_markers(app, course) == {"review"}
    # The tools are shown directly, not inside an expander.
    assert not {"Course tools", *TOOL_LABELS} & {item.label for item in app.expander}

    app.button(key="course_tools_back").click().run()
    assert destinations == [STUDY_PLAN_PAGE]


@pytest.mark.parametrize("tool", ["review", "backup", "source"])
def test_only_the_chosen_tool_is_rendered_and_survives_a_rerun(tool):
    course = make_course({"q1": "pending"})
    app = course_tools_page(course, document=material()).run()
    app.button_group(key=choice_key(course)).set_value(tool).run()

    assert not app.exception
    assert tool_markers(app, course) == {tool}
    app.run()
    assert not app.exception
    assert app.button_group(key=choice_key(course)).value == tool
    assert tool_markers(app, course) == {tool}


def test_clicking_the_chosen_tool_again_keeps_it_on_screen():
    course = make_course({"q1": "pending"})
    app = course_tools_page(course, "backup").run()
    app.button_group(key=choice_key(course)).set_value(None).run()

    assert not app.exception
    assert app.button_group(key=choice_key(course)).value == "backup"
    assert tool_markers(app, course) == {"backup"}


def test_course_tools_page_without_a_course(monkeypatch):
    links = []
    monkeypatch.setattr(st, "page_link", lambda page, label=None, **kwargs: links.append((page, label)))
    app = AppTest.from_file(str(COURSE_TOOLS_PATH)).run()

    assert not app.exception
    assert [item.value for item in app.info] == ["Load a course from the dashboard to start studying."]
    assert links == [("pages/0_Dashboard.py", "Back to Dashboard")]
    assert not app.get("button_group")


# ---- Review and edit questions on the new page --------------------------------------

def test_review_list_shows_plain_status_words_and_pending_first():
    course = make_course({"q1": "pending", "q3": "flagged", "q4": "approved", "q2": "pending"})
    course.learning_state["question_reviews"].pop("q2")
    app = course_tools_page(course).run()

    assert not app.exception
    picker = app.selectbox(key="editor_question_c1")
    assert picker.label == "Question to review"
    assert picker.options == [
        "Needs check · Question 1?",
        "Question 2?",
        "Flagged · Question 3?",
        "Approved · Question 4?",
    ]
    assert not any("[" in option or "legacy" in option.lower() for option in picker.options)
    assert (
        "Check the answer and explanation before approving; edits never change past results."
        in [item.value for item in app.caption]
    )
    # The classification stays tucked away, collapsed.
    classification = next(item for item in app.expander if item.label == "Question classification (advanced)")
    assert not classification.proto.expanded


def test_picking_another_question_loads_it_into_the_form():
    course = make_course({"q1": "pending"})
    app = course_tools_page(course).run()
    app.selectbox(key="editor_question_c1").set_value("q3").run()

    assert not app.exception
    assert app.text_area[0].value == "Question 3?"
    assert [box.value for box in app.text_input][:4] == ["a", "b", "c", "d"]


def test_editing_and_approving_saves_a_new_version_and_says_so():
    course = make_course({"q1": "pending"})
    app = course_tools_page(course).run()
    app.text_area[1].set_value("A corrected explanation.")
    next(item for item in app.radio if item.label == "Correct answer").set_value(2)
    next(button for button in app.button if button.label == "Save review").click().run()

    assert not app.exception
    saved = app.session_state["current_course"]
    revised = saved.questions[-1]
    assert revised.version_of == "q1"
    assert revised.explanation == "A corrected explanation." and revised.correct_index == 2
    assert status_for(saved, "q1") == "superseded"
    assert status_for(saved, revised.id) == "approved"
    assert revised in available_questions(saved)
    assert [item.value for item in app.success] == ["Question review saved."]
    # Still on the review tool after the save.
    assert app.button_group(key=choice_key(course)).value == "review"


def test_flagging_a_question_keeps_it_out_of_practice():
    course = make_course({"q1": "pending"})
    app = course_tools_page(course).run()
    next(item for item in app.radio if item.label == "Review decision").set_value("Flag as problematic")
    next(button for button in app.button if button.label == "Save review").click().run()

    assert not app.exception
    saved = app.session_state["current_course"]
    assert status_for(saved, "q1") == "flagged"
    assert saved.questions == course.questions
    assert "q1" not in {question.id for question in available_questions(saved)}


@pytest.mark.parametrize(
    ("choice", "stored"),
    [("untagged", None), ("computation", "computation"), ("conceptual", "conceptual")],
)
def test_classification_choice_is_saved_with_untagged_as_none(choice, stored):
    course = make_course({"q1": "pending"})
    course.questions[0].cognitive_dimension = "computation"
    app = course_tools_page(course).run()
    dimension = next(item for item in app.radio if item.label == "Learning DNA evidence type")
    assert dimension.options == ["Untagged", "Computation", "Conceptual understanding"]
    assert dimension.value == "computation"
    dimension.set_value(choice)
    next(button for button in app.button if button.label == "Save review").click().run()

    assert not app.exception
    saved = app.session_state["current_course"]
    # An unchanged question keeps its id; a changed one gets a new version.
    current = [question for question in saved.questions if (question.version_of or question.id) == "q1"][-1]
    assert current.cognitive_dimension == stored
    assert status_for(saved, current.id) == "approved"


def test_invalid_edit_shows_the_error_and_saves_nothing():
    course = make_course({"q1": "pending"})
    app = course_tools_page(course).run()
    app.text_input[1].set_value("a")
    next(button for button in app.button if button.label == "Save review").click().run()

    assert not app.exception
    assert [item.value for item in app.error] == [
        "Question, explanation and four distinct options are required."
    ]
    assert app.session_state["current_course"] == course
    assert not app.success


def test_invalid_edit_error_is_translated(monkeypatch):
    pin_chinese(monkeypatch)
    app = course_tools_page(make_chinese_course(), chinese=True).run()
    app.text_input[1].set_value("一")
    next(button for button in app.button if button.label == "保存审核").click().run()

    assert not app.exception
    assert [item.value for item in app.error] == ["题干、解析和四个互不相同的选项都必须填写。"]
    assert english_words(visible_texts(app)) == []


@pytest.mark.parametrize(
    "reviews",
    [
        {f"q{index}": "approved" for index in range(1, 5)},
        {f"q{index}": "pending" for index in range(1, 5)},
        None,
    ],
    ids=["no-pending", "only-pending", "no-questions"],
)
@pytest.mark.parametrize("tool", ["review", "backup", "source"])
def test_page_renders_for_any_mix_of_questions(reviews, tool):
    course = make_course(reviews, questions=reviews is not None)
    app = course_tools_page(course, tool).run()

    assert not app.exception
    assert tool_markers(app, course) == {tool}
    if tool == "review":
        if reviews is None:
            assert "No questions available for review." in [item.value for item in app.caption]
            assert not app.selectbox
        else:
            assert len(app.selectbox(key="editor_question_c1").options) == 4


# ---- Backup and source material on the new page ---------------------------------------

def test_backup_tool_shows_the_save_and_restore_controls():
    course = make_course()
    anonymous = course_tools_page(course, "backup").run()
    assert not anonymous.exception
    assert "Log in to back up this course." in [item.value for item in anonymous.caption]
    assert anonymous.button(key="database_save_c1").disabled
    assert anonymous.button(key="database_restore_c1").disabled

    signed_in = course_tools_page(course, "backup", signed_in=True).run()
    assert not signed_in.exception
    assert "Back up this course to your account." in [item.value for item in signed_in.caption]
    assert not signed_in.button(key="database_save_c1").disabled
    assert not signed_in.button(key="database_restore_c1").disabled


def test_source_tool_shows_the_saved_text_and_delete_form():
    course = make_course()
    app = course_tools_page(course, "source", document=material()).run()

    assert not app.exception
    captions = [item.value for item in app.caption]
    assert "lecture.pdf" in captions
    assert (
        "The text from your material is saved with this course. The original uploaded file is not stored."
        in captions
    )
    saved_text = next(item for item in app.expander if item.label == "Read saved text")
    assert not saved_text.proto.expanded
    assert [item.value for item in saved_text.get("text")] == ["Real source."]
    assert app.checkbox(key="confirm_material_delete_c1").label == "Delete this course's saved material"
    assert app.button(key="delete_material_c1").label == "Delete saved material"

    empty = course_tools_page(course, "source").run()
    assert not empty.exception
    assert "No saved material for this course." in [item.value for item in empty.caption]
    assert not empty.checkbox


def test_deleting_material_says_so_and_stays_on_the_source_tool():
    course = make_course()
    app = course_tools_page(course, "source", document=material()).run()
    app.checkbox(key="confirm_material_delete_c1").check().run()
    app.button(key="delete_material_c1").click().run()

    assert not app.exception
    assert "course_document_c1" not in app.session_state
    assert [item.value for item in app.success] == ["Saved material deleted."]
    assert app.button_group(key=choice_key(course)).value == "source"
    assert "No saved material for this course." in [item.value for item in app.caption]


# ---- Chinese interface ------------------------------------------------------------

@pytest.mark.parametrize("tool", ["review", "backup", "source"])
@pytest.mark.parametrize("signed_in", [False, True])
def test_course_tools_page_in_chinese_has_no_english(tool, signed_in):
    course = make_chinese_course()
    app = course_tools_page(
        course, tool, chinese=True, signed_in=signed_in, document=material("讲义"),
    ).run()

    assert not app.exception
    assert app.title[0].value == "课程工具"
    assert app.button(key="course_tools_back").label == "返回学习计划"
    choice = app.button_group(key=choice_key(course))
    assert choice.options == ["检查和编辑题目", "账户备份与恢复", "来源资料"]
    assert choice.proto.label == "选择工具"
    assert tool_markers(app, course) == {tool}
    assert english_words(visible_texts(app)) == []


def test_chinese_review_form_and_save_notice(monkeypatch):
    pin_chinese(monkeypatch)
    course = make_chinese_course()
    app = course_tools_page(course, chinese=True).run()

    assert not app.exception
    assert [box.label for box in app.text_input][:4] == ["选项 A", "选项 B", "选项 C", "选项 D"]
    decision = next(item for item in app.radio if item.value == "Approve")
    assert decision.label == "审核决定"
    assert decision.options == ["批准", "标记为有问题"]
    assert app.selectbox(key="editor_question_c1").options[0] == "待检查 · 第1题是什么？"
    next(button for button in app.button if button.label == "保存审核").click().run()

    assert not app.exception
    assert [item.value for item in app.success] == ["题目审核已保存。"]
    assert english_words(visible_texts(app)) == []


def test_chinese_source_tool_names_material_without_a_filename():
    course = make_chinese_course()
    app = course_tools_page(course, "source", chinese=True, document=material(None)).run()

    assert not app.exception
    assert "课程资料" in [item.value for item in app.caption]
    app.button(key="delete_material_c1").click().run()
    assert not app.exception
    assert english_words(visible_texts(app)) == []
