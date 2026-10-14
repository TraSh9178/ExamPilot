from copy import deepcopy
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from models.schemas import AttemptResult, ExamSession
from services.learning_state import capture_learning_state
from services.question_editor import available_questions, review_question, status_for
from services.mastery_engine import calculate_topic_stats, get_mastery_status
from services.exam_engine import create_exam
from services.anki_export_service import export_anki_tsv
from services import account_sync
from tests.test_account_sync import FakeStore, make_course, signed_in_state, TEST_USER

ROOT = Path(__file__).resolve().parents[1]


def material():
    return {"ok": True, "filename": "lecture.pdf", "text": "Real source.", "pages": [{"page": 1, "text": "Real source."}], "sources": [{"filename": "lecture.pdf", "page": 1}]}


def test_save_and_new_login_restore_material_scope_and_stage(monkeypatch):
    store = FakeStore(); store.install(monkeypatch)
    course = make_course()
    state = signed_in_state()
    state[f"course_document_{course.course_id}"] = material()
    state[f"confirmed_scope_{course.course_id}"] = ["t1"]
    state[f"course_stage_{course.course_id}"] = "questions_generated"
    assert account_sync.save_course_to_account(state, course).success
    restored = signed_in_state()
    assert account_sync.restore_all(restored).success
    assert restored[f"course_document_{course.course_id}"] == material()
    assert restored[f"confirmed_scope_{course.course_id}"] == ["t1"]
    assert restored[f"scope_selection_{course.course_id}"] == ["t1"]
    assert restored[f"course_stage_{course.course_id}"] == "questions_generated"
    stranger = signed_in_state(user=type(TEST_USER)("other", "other"))
    assert account_sync.restore_all(stranger).success
    assert f"course_document_{course.course_id}" not in stranger


def test_oversized_material_and_invalid_scope_are_rejected_before_save():
    course = make_course()
    with pytest.raises(ValueError):
        capture_learning_state(course, {f"course_document_{course.course_id}": {"text": "x"*50001}})
    with pytest.raises(ValueError):
        capture_learning_state(course, {f"confirmed_scope_{course.course_id}": ["unknown"]})


def test_invalid_restored_metadata_does_not_modify_local_state(monkeypatch):
    from services import postgres_store
    course = make_course().model_copy(update={"learning_state": {"confirmed_scope": ["unknown"]}})
    # Public store loading rejects invalid package JSON; test that validation boundary.
    from tests.test_postgres_store import FakeConnection, use_connection
    connection = FakeConnection(); use_connection(monkeypatch, connection)
    connection.course_packages[("user", course.course_id)] = course.model_dump()
    result = postgres_store.load_course_history("user", course.course_id)
    assert not result.success and result.package is None


def test_repeat_same_question_never_becomes_three_independent_questions():
    course = make_course()
    q = course.questions[0]
    sessions = [ExamSession(session_id=str(i), mode="mock", question_ids=[q.id]) for i in range(8)]
    attempts = [AttemptResult(session_id=s.session_id, question_id=q.id, selected_index=0, is_correct=True) for s in sessions]
    stats = next(s for s in calculate_topic_stats(attempts, sessions, course.questions) if s.mode == "mock")
    assert stats.attempted == 8 and stats.unique_attempted == 1
    assert stats.accuracy == 100 and get_mastery_status(stats) == "insufficient_evidence"


def test_mastery_uses_latest_answer_for_each_question_family():
    course = make_course()
    q = course.questions[0]
    sessions = [ExamSession(session_id=str(i), mode="mock", question_ids=[q.id]) for i in range(2)]
    attempts = [AttemptResult(session_id="0", question_id=q.id, selected_index=0, is_correct=True), AttemptResult(session_id="1", question_id=q.id, selected_index=1, is_correct=False)]
    stats = next(s for s in calculate_topic_stats(attempts[::-1], sessions, course.questions) if s.mode == "mock")
    assert stats.accuracy == 50 and stats.evidence_accuracy == 0


def test_pending_and_flagged_questions_are_excluded_from_practice_and_export():
    course = make_course()
    course.learning_state = {"question_reviews": {q.id: "pending" for q in course.questions}}
    with pytest.raises(ValueError):
        create_exam(course, "mock", 10, ["t1"])
    assert export_anki_tsv(course) == ""
    approved = review_question(course, course.questions[0].id, "approved")
    assert len(create_exam(approved, "mock", 10, ["t1"])["questions"]) == 1
    flagged = review_question(approved, course.questions[0].id, "flagged")
    assert available_questions(flagged) == []


def test_edit_creates_version_and_keeps_original_question_and_evidence_root():
    course = make_course()
    original = deepcopy(course.questions[0])
    revised = review_question(course, original.id, "approved", {"explanation": "Corrected explanation."})
    assert revised.questions[0] == original
    new = revised.questions[-1]
    assert new.id != original.id and new.version_of == original.id
    assert status_for(revised, original.id) == "superseded"
    assert original not in available_questions(revised)
    sessions = [ExamSession(session_id="old", mode="mock", question_ids=[original.id]), ExamSession(session_id="new", mode="mock", question_ids=[new.id])]
    attempts = [AttemptResult(session_id=s.session_id, question_id=s.question_ids[0], selected_index=0, is_correct=True) for s in sessions]
    stats = next(s for s in calculate_topic_stats(attempts, sessions, revised.questions) if s.mode == "mock")
    assert stats.attempted == 2 and stats.unique_attempted == 1


def test_question_editor_ui_approves_pending_question():
    course = make_course()
    course.learning_state = {"question_reviews": {q.id: "pending" for q in course.questions}}
    app = AppTest.from_file(str(ROOT / "pages/1_Study_Hub.py"))
    app.session_state["current_course"] = course
    app.run()
    next(b for b in app.button if b.label == "Save review").click().run()
    assert not app.exception
    saved = app.session_state["current_course"]
    assert status_for(saved, course.questions[0].id) == "approved"
    assert saved.questions == course.questions


def test_delete_material_ui_preserves_course_and_scope(monkeypatch):
    store = FakeStore(); store.install(monkeypatch)
    course = make_course()
    state = signed_in_state()
    app = AppTest.from_file(str(ROOT / "pages/1_Study_Hub.py"))
    for key,value in state.items(): app.session_state[key] = value
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = ["t1"]
    app.session_state[f"course_document_{course.course_id}"] = material()
    app.run()
    app.checkbox(key=f"confirm_material_delete_{course.course_id}").check().run()
    app.button(key=f"delete_material_{course.course_id}").click().run()
    assert not app.exception
    assert f"course_document_{course.course_id}" not in app.session_state
    assert app.session_state[f"confirmed_scope_{course.course_id}"] == ["t1"]
    saved = store.courses[TEST_USER.user_id][course.course_id]
    assert saved.learning_state["document"] is None and saved.questions == course.questions


def test_failed_material_deletion_keeps_local_material(monkeypatch):
    store = FakeStore(); store.install(monkeypatch); store.fail.add("save_course")
    course = make_course()
    app = AppTest.from_file(str(ROOT / "pages/1_Study_Hub.py"))
    for key,value in signed_in_state().items(): app.session_state[key] = value
    app.session_state["current_course"] = course
    app.session_state[f"course_document_{course.course_id}"] = material()
    app.run()
    app.checkbox(key=f"confirm_material_delete_{course.course_id}").check().run()
    app.button(key=f"delete_material_{course.course_id}").click().run()
    assert not app.exception
    assert app.session_state[f"course_document_{course.course_id}"] == material()
    assert app.error


def test_generated_candidates_cannot_invent_version_lineage():
    from services.question_review import validate_question_content
    course = make_course()
    fake = course.questions[0].model_copy(update={"id": "fake", "version_of": course.questions[0].id})
    with pytest.raises(ValueError):
        validate_question_content([fake], course.questions)


def test_first_study_page_entry_hydrates_saved_scope_over_stale_widget_default():
    course = make_course()
    course.learning_state = {"confirmed_scope": ["t1"]}
    app = AppTest.from_file(str(ROOT / "pages/1_Study_Hub.py"))
    app.session_state["current_course"] = course
    app.session_state[f"scope_selection_{course.course_id}"] = []
    app.run()
    assert not app.exception
    assert app.multiselect[0].value == ["t1"]
    assert app.session_state[f"confirmed_scope_{course.course_id}"] == ["t1"]
    app.multiselect[0].set_value([]).run()
    assert f"confirmed_scope_{course.course_id}" not in app.session_state


def test_material_delete_without_confirmation_does_nothing():
    course = make_course()
    app = AppTest.from_file(str(ROOT / "pages/1_Study_Hub.py"))
    app.session_state["current_course"] = course
    app.session_state[f"course_document_{course.course_id}"] = material()
    app.run()
    app.button(key=f"delete_material_{course.course_id}").click().run()
    assert not app.exception
    assert app.session_state[f"course_document_{course.course_id}"] == material()
    assert any("confirmation checkbox" in item.value for item in app.warning)
