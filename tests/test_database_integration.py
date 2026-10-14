"""Opt-in real PostgreSQL tests, each in a new isolated schema.

EXAMPILOT_TEST_DATABASE_URL must point to a disposable local server.
No .env file is read and no production connection is used.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services import postgres_store as store
from services.database_migrations import apply_migrations, MigrationError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(monkeypatch):
    dsn = os.getenv("EXAMPILOT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set EXAMPILOT_TEST_DATABASE_URL to a disposable local PostgreSQL server.")
    host = conninfo_to_dict(dsn).get("host", "")
    if host not in {"localhost", "127.0.0.1", "::1"} and not host.startswith("/private/tmp/"):
        pytest.fail("Integration tests require an explicitly configured local PostgreSQL server.")
    schema = "exampilot_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(dsn, options=f"-c search_path={schema}", prepare_threshold=None)
    monkeypatch.setattr(store, "_connect", connect)
    try:
        with connect() as connection:
            apply_migrations(connection)
        yield connect
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def course():
    return StudyPackage.model_validate_json((ROOT / "data/calculus_i_demo.json").read_text())


def exam(course, sid="practice", selected=None):
    question = course.questions[0]
    pick = question.correct_index if selected is None else selected
    session = ExamSession(session_id=sid, mode="mock", question_ids=[question.id])
    attempts = [AttemptResult(session_id=sid, question_id=question.id,
                              selected_index=pick, is_correct=pick == question.correct_index)]
    return session, attempts


def reject_answer_writes(connect):
    with connect() as connection:
        connection.execute("""
            CREATE FUNCTION reject_answers() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected test failure'; END $$;
            CREATE TRIGGER reject_answers BEFORE INSERT ON attempt_results
            FOR EACH ROW EXECUTE FUNCTION reject_answers();
        """, prepare=False)


def test_real_transaction_rolls_back_course_session_and_answers(db, course):
    reject_answer_writes(db)
    assert not store.save_course_history("alice", course, [exam(course)]).success
    with db() as connection:
        for table in ("courses", "exam_sessions", "attempt_results", "demo_users"):
            assert connection.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0


def test_real_batch_failure_preserves_previously_saved_history(db, course):
    assert store.save_course_history("alice", course, [exam(course, "old")]).success
    reject_answer_writes(db)
    renamed = course.model_copy(update={"course_name": "Uncommitted name"})
    assert not store.save_course_history("alice", renamed, [exam(course, "new")]).success
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success and restored.package.course_name == course.course_name
    assert [session.session_id for session in restored.sessions] == ["old"]


def test_real_concurrent_identical_retries_create_one_session(db, course):
    barrier = Barrier(2)
    def save():
        barrier.wait(timeout=10)
        return store.save_course_history("alice", course, [exam(course)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert all(result.success for result in results)
    with db() as connection:
        assert connection.execute("SELECT count(*) FROM exam_sessions").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM attempt_results").fetchone()[0] == 1


def test_real_cross_course_session_collision_cannot_mix_records(db, course):
    other = course.model_copy(update={"course_id": "other-course"})
    barrier = Barrier(2)
    def save(package):
        barrier.wait(timeout=10)
        return store.save_course_history("alice", package, [exam(package)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [course, other]))
    assert sum(result.success for result in results) == 1
    with db() as connection:
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM exam_sessions").fetchone()[0] == 1


def test_real_users_with_shared_identifiers_remain_isolated(db, course):
    first = exam(course)
    second = exam(course, selected=(course.questions[0].correct_index + 1) % 4)
    assert store.save_course_history("alice", course, [first]).success
    assert store.save_course_history("bob", course, [second]).success
    alice = store.load_course_history("alice", course.course_id)
    bob = store.load_course_history("bob", course.course_id)
    assert alice.success and bob.success
    assert alice.attempts == first[1] and bob.attempts == second[1]
    assert store.list_saved_courses("stranger").courses == []
    assert store.load_course_history("stranger", course.course_id).package is None
    assert not store.save_exam_result("stranger", course.course_id, *first).success


def test_real_conflicting_retry_preserves_original_snapshot(db, course):
    original = exam(course)
    assert store.save_course_history("alice", course, [original]).success
    changed = exam(course, selected=(course.questions[0].correct_index + 1) % 4)
    assert not store.save_course_history("alice", course, [changed]).success
    assert store.load_course_history("alice", course.course_id).attempts == original[1]


def test_real_new_question_version_preserves_historical_results(db, course):
    original = exam(course)
    assert store.save_course_history("alice", course, [original]).success
    changed = course.questions[0].model_copy(update={"question": "Changed question"})
    invalid = course.model_copy(update={"questions": [changed]})
    assert not store.save_course("alice", invalid).success
    revised = changed.model_copy(update={"id": "new-version"})
    appended = course.model_copy(update={"questions": [revised]})
    assert store.save_course("alice", appended).success
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success and restored.attempts == original[1]
    assert {q.id for q in restored.package.questions} == {q.id for q in course.questions} | {"new-version"}


def test_real_corrupt_grade_and_incomplete_history_fail_closed(db, course):
    session, attempts = exam(course)
    assert store.save_course_history("alice", course, [(session, attempts)]).success
    with db() as connection:
        connection.execute("UPDATE attempt_results SET is_correct = FALSE")
    assert not store.load_course_history("alice", course.course_id).success
    with db() as connection:
        connection.execute("DELETE FROM attempt_results")
    assert not store.load_course_history("alice", course.course_id).success


def test_real_migrations_are_repeatable_and_detect_changed_history(db, tmp_path):
    with db() as connection:
        assert apply_migrations(connection) == []
    with db() as connection:
        connection.execute("UPDATE exampilot_schema_migrations SET checksum = 'tampered'")
    with db() as connection, pytest.raises(MigrationError):
        apply_migrations(connection)


def test_real_migration_failure_rolls_back_ddl_and_ledger(db, tmp_path):
    from services.database_migrations import MIGRATION_DIRECTORY
    for source in MIGRATION_DIRECTORY.glob("*.sql"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / "003_deliberate_failure.sql").write_text("CREATE TABLE should_rollback (id INT); SELECT no_such_function();")
    with db() as connection, pytest.raises(psycopg.Error):
        apply_migrations(connection, tmp_path)
    with db() as connection:
        assert connection.execute("SELECT to_regclass('should_rollback')").fetchone()[0] is None
        assert connection.execute("SELECT count(*) FROM exampilot_schema_migrations").fetchone()[0] == 2


def test_real_schema_rejects_bad_new_course_identity(db, course):
    assert store.save_course("alice", course).success
    with db() as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute("UPDATE courses SET course_id = 'mismatched'")


def test_real_backup_restores_into_a_separate_database(db, course, tmp_path, monkeypatch):
    import subprocess
    from psycopg.conninfo import make_conninfo
    binary_directory = os.getenv("EXAMPILOT_TEST_PG_BIN")
    if not binary_directory:
        pytest.skip("Set EXAMPILOT_TEST_PG_BIN to local PostgreSQL tools for recovery verification.")
    original = exam(course)
    assert store.save_course_history("alice", course, [original]).success
    with db() as connection:
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
    dsn = os.environ["EXAMPILOT_TEST_DATABASE_URL"]
    archive = tmp_path / "learning-backup.dump"
    parameters = conninfo_to_dict(dsn)
    environment = dict(os.environ)
    for key, variable in (("host", "PGHOST"), ("port", "PGPORT"), ("user", "PGUSER"), ("dbname", "PGDATABASE"), ("password", "PGPASSWORD"), ("sslmode", "PGSSLMODE")):
        if key in parameters:
            environment[variable] = parameters[key]
    subprocess.run([str(Path(binary_directory) / "pg_dump"), "--format=custom", "--schema", schema, "--file", str(archive)], env=environment, check=True, capture_output=True)
    recovered_database = "exampilot_recovered_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(recovered_database)))
    recovery_dsn = make_conninfo(dsn, dbname=recovered_database)
    try:
        subprocess.run([str(Path(binary_directory) / "pg_restore"), "--exit-on-error", "--no-owner", "--no-privileges", "--dbname", recovered_database, str(archive)], env={**environment, "PGDATABASE": recovered_database}, check=True, capture_output=True)
        def connect_recovered():
            return psycopg.connect(recovery_dsn, options=f"-c search_path={schema}", prepare_threshold=None)
        monkeypatch.setattr(store, "_connect", connect_recovered)
        restored = store.load_course_history("alice", course.course_id)
        assert restored.success and restored.package.model_dump(exclude={"learning_state"}) == course.model_dump(exclude={"learning_state"})
        assert restored.sessions == [original[0]] and restored.attempts == original[1]
        assert store.list_saved_courses("bob").courses == []
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(recovered_database)))


def test_real_migrations_preserve_preexisting_learning_records(db, course):
    original = exam(course)
    assert store.save_course_history("alice", course, [original]).success
    with db() as connection:
        connection.execute("""
            DROP TABLE exampilot_schema_migrations;
            ALTER TABLE courses DROP CONSTRAINT course_package_identity_matches;
            ALTER TABLE exam_sessions DROP CONSTRAINT session_questions_not_empty;
        """, prepare=False)
    with db() as connection:
        assert len(apply_migrations(connection)) == 2
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success and restored.package.model_dump(exclude={"learning_state"}) == course.model_dump(exclude={"learning_state"})
    assert restored.sessions == [original[0]] and restored.attempts == original[1]


def test_real_material_scope_review_state_restore_and_delete(db, course):
    from services.learning_state import capture_learning_state, restored_learning_state
    from services.question_editor import review_question, status_for
    document = {"filename": "lecture.pdf", "text": "Original material.", "pages": [{"page": 1, "text": "Original material."}]}
    snapshot = capture_learning_state(course, {f"course_document_{course.course_id}": document, f"confirmed_scope_{course.course_id}": [course.topics[0].id]})
    snapshot = review_question(snapshot, course.questions[0].id, "flagged")
    assert store.save_course_history("alice", snapshot, []).success
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success
    updates = restored_learning_state(restored.package)
    assert updates[f"course_document_{course.course_id}"] == document
    assert updates[f"confirmed_scope_{course.course_id}"] == [course.topics[0].id]
    assert status_for(restored.package, course.questions[0].id) == "flagged"
    assert store.load_course_history("bob", course.course_id).package is None
    metadata = dict(restored.package.learning_state); metadata["document"] = None
    cleared = restored.package.model_copy(update={"learning_state": metadata})
    assert store.save_course("alice", cleared).success
    assert store.load_course("alice", course.course_id).package.learning_state["document"] is None


def test_real_material_update_rolls_back_when_answer_save_fails(db, course):
    first = course.model_copy(update={"learning_state": {"document": {"filename": "a.txt", "text": "original"}}})
    assert store.save_course("alice", first).success
    reject_answer_writes(db)
    second = course.model_copy(update={"learning_state": {"document": {"filename": "b.txt", "text": "changed"}}})
    assert not store.save_course_history("alice", second, [exam(course)]).success
    assert store.load_course("alice", course.course_id).package.learning_state["document"]["text"] == "original"


def test_real_latest_evidence_chronology_survives_batch_restore(db, course):
    from services.mastery_engine import get_mastery_status
    old = exam(course, "z-old")
    new = exam(course, "a-new", selected=(course.questions[0].correct_index+1)%4)
    assert store.save_course_history("alice", course, [old, new]).success
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success
    assert [s.session_id for s in restored.sessions] == ["z-old", "a-new"]
    stat = next(s for s in restored.topic_stats if s.topic_id == course.questions[0].topic_id and s.mode == "mock")
    assert stat.attempted == 2 and stat.unique_attempted == 1 and stat.evidence_accuracy == 0
    assert get_mastery_status(stat) == "insufficient_evidence"


def test_real_edited_question_preserves_old_grade_and_family(db, course):
    from services.question_editor import review_question, available_questions
    original = exam(course, "original")
    assert store.save_course_history("alice", course, [original]).success
    revised = review_question(course, course.questions[0].id, "approved", {"explanation": "Manually checked explanation."})
    assert store.save_course("alice", revised).success
    restored = store.load_course_history("alice", course.course_id)
    assert restored.success and restored.attempts == original[1]
    assert restored.package.questions[0] == course.questions[0]
    assert restored.package.questions[-1].version_of == course.questions[0].id
    assert course.questions[0].id not in {q.id for q in available_questions(restored.package)}
