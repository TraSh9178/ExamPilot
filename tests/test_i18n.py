"""Interface language changes presentation, not course or exam identifiers."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.i18n import LANGUAGE_KEY
from services.auth_service import AuthUser
from services.auth_session import logout_session, start_authenticated_session
from tests.test_demo_courses import load_demo

ROOT = Path(__file__).resolve().parents[1]


def test_language_preference_survives_login_and_logout_without_study_data() -> None:
    state = {LANGUAGE_KEY: True, "current_course": object(), "login_password": "secret"}
    start_authenticated_session(state, AuthUser("test-user", "test-name"))
    assert state[LANGUAGE_KEY] is True
    assert "current_course" not in state
    assert "login_password" not in state
    logout_session(state)
    assert state == {LANGUAGE_KEY: True}


def test_chinese_progress_keeps_original_course_data() -> None:
    course = load_demo("sample_course.json")
    app = AppTest.from_file(str(ROOT / "pages" / "3_Performance.py"))
    app.session_state[LANGUAGE_KEY] = True
    app.session_state["current_course"] = course
    app.run()

    assert not app.exception
    assert app.title[0].value == "学习进度"
    assert any(item.label == "正确率" for item in app.metric)
    # The demo course shows the example report until its first graded session.
    assert "示例 · 各知识点掌握情况" in [item.value for item in app.subheader]
    assert any("Supply and Demand" in item.value and "已掌握" in item.value for item in app.markdown)
    assert app.session_state["current_course"].course_id == course.course_id


@pytest.mark.parametrize(
    ("filename", "expected_title"),
    [
        ("1_Study_Hub.py", "学习计划"),
        ("2_Practice_Center.py", "练习"),
        ("4_Knowledge_Graph.py", "知识图谱"),
        ("5_Export_Anki.py", "复习卡片"),
        ("6_Concept_Lab.py", "概念实验室"),
    ],
)
def test_chinese_page_headings_without_rewriting_course(
    filename: str, expected_title: str
) -> None:
    course = load_demo("sample_course.json")
    app = AppTest.from_file(str(ROOT / "pages" / filename))
    app.session_state[LANGUAGE_KEY] = True
    app.session_state["current_course"] = course
    app.run()

    assert not app.exception
    assert app.title[0].value == expected_title
    assert app.session_state["current_course"].course_id == course.course_id


def test_language_survives_widget_cleanup_and_can_switch_back() -> None:
    app = AppTest.from_string("""
import streamlit as st
from services.i18n import render_language_control, tr
if st.session_state.get("show_control", True):
    render_language_control()
st.title(tr("Practice"))
""").run()
    app.toggle[0].set_value(True).run()
    assert app.title[0].value == "练习"
    app.session_state["show_control"] = False
    app.run().run()
    assert app.session_state[LANGUAGE_KEY] is True
    assert app.title[0].value == "练习"
    app.session_state["show_control"] = True
    app.run()
    assert app.toggle[0].value is True
    app.toggle[0].set_value(False).run()
    assert app.title[0].value == "Practice"
