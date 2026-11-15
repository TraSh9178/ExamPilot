"""Check new demo content, review gating, and real topic practice selection."""
import contextlib
import io
import json
from collections import Counter
from pathlib import Path

import pytest

from models.schemas import StudyPackage
from services.exam_engine import create_exam, grade_exam
from services.question_editor import available_questions, review_question
from services.question_review import normalized_text

DATA = Path(__file__).resolve().parents[1] / 'data'
FILES = ['calculus_i_demo.json', 'sample_course.json', 'demo_python_basics.json']


def load(filename):
    return StudyPackage.model_validate_json((DATA / filename).read_text(encoding='utf-8'))


@pytest.mark.parametrize('filename,old_count', zip(FILES, [3, 3, 9]))
def test_bank_has_ten_distinct_questions_per_topic_with_review_gate(filename, old_count):
    course = load(filename)
    expected = {t.id: (10 if i < 3 or filename != 'calculus_i_demo.json' else 3) for i, t in enumerate(course.topics)}
    assert Counter(q.topic_id for q in course.questions) == expected
    assert len({normalized_text(q.question) for q in course.questions}) == sum(expected.values())
    for question in course.questions:
        assert question.question.strip() and question.explanation.strip()
        assert len({normalized_text(option) for option in question.options}) == 4
        assert question.source_pages == []  # Original demo content has no source-page claims.
    assert [q.id for q in available_questions(course)] == [q.id for q in course.questions[:old_count]]
    assert course.learning_state['question_reviews'] == {
        q.id: 'pending' for q in course.questions[old_count:]
    }
    for question in course.questions[old_count:]:
        course = review_question(course, question.id, 'approved')
    for topic in course.topics:
        exam = create_exam(course, 'topic', 10, [topic.id], topic.id)
        assert len(exam['questions']) == expected[topic.id]
        assert {q.topic_id for q in exam['questions']} == {topic.id}
        assert len(set(exam['session'].question_ids)) == expected[topic.id]
        result = grade_exam(exam['session'], exam['questions'], {
            q.id: q.correct_index for q in exam['questions']
        })
        assert result['correct_count'] == result['total_count'] == expected[topic.id]


# Execute only fixed, repository-authored teaching snippets, never external inputs.
PYTHON_CASES = [
    ('python-basics-q10', 'x = 3\ny = x\nx = 8\nprint(y)', '3'),
    ('python-basics-q11', 'print(2 + 3 * 4)', '14'),
    ('python-basics-q12', 'print(7 // 2)', '3'),
    ('python-basics-q13', 'print(7 % 2)', '1'),
    ('python-basics-q14', 'print(repr("3" + "4"))', "'34'"),
    ('python-basics-q15', 'x = 5\nx += 2\nprint(x)', '7'),
    ('python-basics-q16', 'print(type(int("12")).__name__)', 'int'),
    ('python-basics-q17', 'x = 0\nif x > 0:\n    print("positive")\nelse:\n    print("not positive")', 'not positive'),
    ('python-basics-q18', 'x = 7\nif x > 5:\n    print("A")\nelif x > 3:\n    print("B")', 'A'),
    ('python-basics-q19', 'print(3 < 5 and 8 < 2)', 'False'),
    ('python-basics-q20', 'print(not (4 == 4))', 'False'),
    ('python-basics-q21', 'print(4 == 4)', 'True'),
    ('python-basics-q22', 'print(0 < 3 < 5)', 'True'),
    ('python-basics-q23', 'x = 4\nif x > 2:\n    print("A")\nif x > 3:\n    print("B")', 'A\nB'),
    ('python-basics-q24', 'for i in range(3):\n    print(i)', '0\n1\n2'),
    ('python-basics-q25', 'total = 0\nfor n in [1, 2, 3]:\n    total += n\nprint(total)', '6'),
    ('python-basics-q26', 'x = 1\nwhile x < 8:\n    x *= 2\nprint(x)', '8'),
    ('python-basics-q27', 'for i in range(5):\n    if i == 2:\n        break\n    print(i)', '0\n1'),
    ('python-basics-q28', 'for i in range(4):\n    if i == 1:\n        continue\n    print(i)', '0\n2\n3'),
    ('python-basics-q29', 'for i in range(2):\n    for j in range(3):\n        print(i, j)', '0 0\n0 1\n0 2\n1 0\n1 1\n1 2'),
    ('python-basics-q30', 'count = 0\nfor i in range(0):\n    count += 1\nprint(count)', '0'),
]
PYTHON_ANSWERS = [
    '3', '14', '3', '1', 'The string "34"', '7', 'int("12")',
    'not positive', 'A', 'False', 'False', '==', 'True', 'A then B',
    '0, 1, 2', '6', '8', '0, 1', '0, 2, 3', '6', '0',
]


@pytest.mark.parametrize('case,answer', zip(PYTHON_CASES, PYTHON_ANSWERS))
def test_python_answers_against_actual_execution(case, answer):
    qid, code, expected = case
    question = next(q for q in load(FILES[2]).questions if q.id == qid)
    assert question.options[question.correct_index] == answer
    # For output questions execute the exact code printed in the stem.
    if '\n' in question.question:
        assert question.question.split('\n', 1)[1] == code
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(code, {'__builtins__': {'print': print, 'range': range, 'int': int, 'type': type, 'repr': repr}})
    assert output.getvalue().strip() == expected


def test_numeric_calculus_answers_against_independent_formulas():
    questions = {q.id: q for q in load(FILES[0]).questions}
    answers = {qid: q.options[q.correct_index] for qid, q in questions.items()}
    assert answers['calc_q005'] == f'{1.99 + 2:g} and {2.01 + 2:g}'
    assert answers['calc_q008'] == str(3**2 + 1)
    f = lambda x: x**3 - 5*x
    assert answers['calc_q013'] == str(3*1**2 - 5).replace('-', '−')
    assert answers['calc_q014'] == str(3*2**2 - 5)
    assert float(answers['calc_q015'].replace('−', '-')) == (f(1.5)-f(1))/0.5
    assert answers['calc_q022'] == str(2**2 - 4*2).replace('-', '−')
    assert answers['calc_q025'] == str(max(x*x - 4*x for x in [0, 2, 3]))
    assert answers['calc_q028'] == '5 and 5'
    assert max(x*(10-x) for x in range(11)) == 5*5
    assert answers['calc_q030'] == str(2*3-4)


def test_numeric_economics_answers():
    questions = {q.id: q for q in load(FILES[1]).questions}
    answer = lambda qid: questions[qid].options[questions[qid].correct_index]
    assert answer('q012') == str(20//4)
    midpoint = abs(((80-100)/90)/((12-10)/11))
    assert answer('q013') == f'{midpoint:.2f}'
    assert answer('q026') == f'{120-70} units'
    assert answer('q027') == f'{100-60} units'


def test_python_historical_review_applies_only_to_original_questions():
    metadata = json.loads((DATA / 'demo_python_basics_metadata.json').read_text(encoding='utf-8'))
    assert metadata['review']['scope']['questions'] == 9
    assert metadata['expansion']['added_questions'] == 21
    assert metadata['expansion']['review_status'] == 'pending'


@pytest.mark.parametrize('filename', FILES)
def test_new_questions_can_be_reviewed_in_existing_study_plan(filename):
    from streamlit.testing.v1 import AppTest

    course = load(filename)
    app = AppTest.from_file(str(DATA.parent / 'pages' / '1_Study_Hub.py'))
    app.session_state['current_course'] = course
    app.session_state[f'confirmed_scope_{course.course_id}'] = [t.id for t in course.topics]
    app.run()
    assert not app.exception
    selector = app.selectbox(key=f'editor_question_{course.course_id}')
    question = next(q for q in course.questions if q.id == selector.value)
    assert course.learning_state['question_reviews'][question.id] == 'pending'
    assert app.text_area[0].value == question.question
    assert app.text_area[1].value == question.explanation
    next(b for b in app.button if b.label == 'Save review').click().run()
    assert not app.exception
    updated = app.session_state['current_course']
    assert updated.learning_state['question_reviews'][question.id] == 'approved'
    assert question.id in {q.id for q in available_questions(updated)}


@pytest.mark.parametrize('filename', FILES)
def test_anki_export_excludes_drafts_then_includes_approved_question(filename):
    import csv
    from services.anki_export_service import export_anki_tsv

    course = load(filename)
    pending = next(q for q in course.questions if q.id in course.learning_state['question_reviews'])
    before = list(csv.reader(io.StringIO(export_anki_tsv(course)), delimiter='\t'))
    assert len(before) == len(available_questions(course))
    assert not any(row[0].startswith(pending.question + '\n') for row in before)
    approved = review_question(course, pending.id, 'approved')
    after = list(csv.reader(io.StringIO(export_anki_tsv(approved)), delimiter='\t'))
    assert len(after) == len(before) + 1
    assert any(row[0].startswith(pending.question + '\n') for row in after)
