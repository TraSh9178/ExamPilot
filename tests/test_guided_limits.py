from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services import guided_limits_ui
from services.exam_engine import grade_exam
from tests.auth_helpers import signed_in_app


ROOT = Path(__file__).resolve().parents[1]
COURSE_ID = guided_limits_ui.DEMO_COURSE_ID


def calculus():
    return StudyPackage.model_validate_json(
        (ROOT / "data" / "calculus_i_demo.json").read_text(encoding="utf-8")
    )


def test_demo_launches_from_dashboard_and_keeps_answer_hints():
    app = signed_in_app(ROOT / "app.py").run()
    app.button(key="try_limits_demo").click().run()
    app.switch_page("pages/2_Practice_Center.py").run()

    assert not app.exception
    active = app.session_state[f"active_practice_{COURSE_ID}"]
    session = active["session"]
    assert session.mode == "topic"
    assert session.question_ids == [guided_limits_ui.QUESTION_ID]
    assert app.session_state[f"confirmed_scope_{COURSE_ID}"] == [guided_limits_ui.TOPIC_ID]
    assert any(button.label == "Show a hint" for button in app.button)


def test_starter_does_not_replace_an_existing_scope():
    course = calculus()
    scope_key = f"confirmed_scope_{COURSE_ID}"
    state = {"courses": [course], scope_key: ["calc_derivatives"]}

    with pytest.raises(ValueError, match="outside the confirmed scope"):
        guided_limits_ui.start_demo(state, course, guided_limits_ui.starter_question(course))

    assert state[scope_key] == ["calc_derivatives"]
    assert f"active_practice_{COURSE_ID}" not in state


def test_guided_review_reports_retry_and_only_shares_when_requested(monkeypatch):
    course = calculus()
    question = guided_limits_ui.starter_question(course)
    state = {"courses": [course]}
    guided_limits_ui.start_demo(state, course, question)
    session = state[f"active_practice_{COURSE_ID}"]["session"]
    result = grade_exam(session, [question], {question.id: 3})
    monkeypatch.setattr(guided_limits_ui, "current_user", lambda _state: SimpleNamespace(user_id="tester"))
    flags = []

    def save_flag(*args):
        flags.append(args)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(guided_limits_ui.learning_radar, "set_flag", save_flag)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from services.guided_limits_ui import render_guided_review\n"
        "render_guided_review(*st.session_state['fixture'])\n"
    )
    app.session_state["fixture"] = (course, session, [question], result)
    app.run()
    key = f"guided_limits_{session.session_id}"
    app.radio(key=f"{key}_reason").set_value("start")
    app.button(key=f"{key}_start").click().run()
    assert flags == []
    app.button(key=f"{key}_flag").click().run()
    assert flags == [("tester", COURSE_ID, guided_limits_ui.TOPIC_ID, "start")]

    app.radio(key=f"{key}_factor").set_value(guided_limits_ui.FACTORS[1])
    app.button(key=f"{key}_check").click().run()
    app.radio(key=f"{key}_transfer").set_value("4")
    app.button(key=f"{key}_finish").click().run()
    assert not app.session_state[key].get("complete")
    app.radio(key=f"{key}_transfer").set_value("8")
    app.button(key=f"{key}_finish").click().run()

    assert not app.exception
    assert app.session_state[key]["complete"]
    assert "Solved after a retry." in [item.value for item in app.caption]
    assert result["correct_count"] == 0
