from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, ExamSession, Question, StudyPackage
from services.learning_dna import comparison, evidence_profile
from services.question_editor import review_question

ROOT = Path(__file__).resolve().parents[1]


def question(qid, dim='computation', **kwargs):
    return Question(id=qid, topic_id='t', question=f'Question {qid}', options=['A','B','C','D'],
                    correct_index=0, explanation='Reason', cognitive_dimension=dim, **kwargs)


def fixture_history():
    questions = [question(f'q{i}', 'computation' if i < 3 else 'conceptual') for i in range(6)]
    session = ExamSession(session_id='s', mode='topic', question_ids=[q.id for q in questions])
    attempts = [AttemptResult(session_id='s', question_id=q.id, selected_index=0 if i<3 else 1,
                              is_correct=i<3) for i,q in enumerate(questions)]
    return questions, [session], attempts


def test_distinct_dimensions_reveal_gap_hidden_by_total_accuracy():
    qs, ss, aa = fixture_history()
    profile, excluded = evidence_profile(aa, ss, qs, 'topic')
    computation, conceptual = profile
    assert excluded == 0
    assert computation.count == conceptual.count == 3
    assert computation.accuracy == 100 and conceptual.accuracy == 0
    assert computation.status == 'Consistent answers'
    assert conceptual.status == 'Needs review'
    assert 'Computation answers are more consistent' in comparison(*profile)
    assert all(row['question_id'] in {'q0','q1','q2'} for row in computation.evidence)


def test_latest_family_answer_not_repetition_or_attempt_order_drives_profile():
    q = question('q')
    ss = [ExamSession(session_id=f's{i}', mode='topic', question_ids=['q']) for i in range(4)]
    aa = [AttemptResult(session_id=s.session_id, question_id='q', selected_index=0 if i<3 else 1,
                        is_correct=i<3) for i,s in enumerate(ss)]
    profile, _ = evidence_profile(list(reversed(aa)), ss, [q], 'topic')
    assert profile[0].count == 1 and profile[0].accuracy == 0
    assert profile[0].status == 'Insufficient evidence'


def test_modes_topics_and_unclassified_responses_remain_separate():
    qs, ss, aa = fixture_history()
    mock = ExamSession(session_id='mock', mode='mock', question_ids=['q0'])
    aa.append(AttemptResult(session_id='mock', question_id='q0', selected_index=1,is_correct=False))
    qs.append(question('untagged', None))
    ss.append(ExamSession(session_id='u', mode='topic', question_ids=['untagged']))
    aa.append(AttemptResult(session_id='u',question_id='untagged',selected_index=0,is_correct=True))
    qs.append(question('other').model_copy(update={'topic_id':'other-topic'}))
    profile, excluded = evidence_profile(aa, [*ss,mock], qs, 'topic')
    assert excluded == 1 and profile[0].accuracy == 100
    assert all(p.count==0 for p in profile if p.topic_id=='other-topic')
    profile, excluded = evidence_profile(aa, [*ss,mock], qs, 'mock')
    assert profile[0].count == 1 and profile[0].accuracy == 0 and excluded == 0


def test_unanswered_latest_response_is_not_claimed_as_dimension_evidence():
    q = question('q')
    s = ExamSession(session_id='s',mode='topic',question_ids=['q'])
    a = AttemptResult(session_id='s',question_id='q',selected_index=None,is_correct=False)
    profile, excluded = evidence_profile([a],[s],[q],'topic')
    assert excluded == 1 and profile[0].count == 0 and profile[0].accuracy is None


def test_edited_version_does_not_add_independent_evidence_or_relabel_history():
    old, new = question('old'), question('new','conceptual',version_of='old')
    ss = [ExamSession(session_id='old-s',mode='topic',question_ids=['old']),
          ExamSession(session_id='new-s',mode='topic',question_ids=['new'])]
    aa = [AttemptResult(session_id=s.session_id,question_id=s.question_ids[0],selected_index=0,is_correct=True) for s in ss]
    profile, _ = evidence_profile(aa[:1], ss, [old,new], 'topic')
    assert profile[0].count == 1 and profile[1].count == 0
    profile, _ = evidence_profile(aa, ss, [old,new], 'topic')
    assert profile[0].count == 0 and profile[1].count == 1


@pytest.mark.parametrize('bad_kind',['duplicate','unknown','outside','cycle','duplicate-session'])
def test_invalid_history_is_rejected(bad_kind):
    qs, ss, aa = fixture_history()
    if bad_kind=='duplicate': aa.append(aa[0])
    if bad_kind=='unknown': aa[0]=aa[0].model_copy(update={'question_id':'missing'})
    if bad_kind=='outside': ss[0]=ss[0].model_copy(update={'question_ids':['q0']})
    if bad_kind=='cycle': qs[0]=qs[0].model_copy(update={'version_of':'q0'})
    if bad_kind=='duplicate-session': ss.append(ss[0])
    with pytest.raises(ValueError): evidence_profile(aa,ss,qs,'topic')


def test_old_question_payload_still_loads_and_invalid_dimension_rejected():
    data=question('q').model_dump(); data.pop('cognitive_dimension')
    assert Question.model_validate(data).cognitive_dimension is None
    with pytest.raises(ValidationError): Question.model_validate({**data,'cognitive_dimension':'intelligence'})


def course_and_history():
    qs,ss,aa=fixture_history()
    course=StudyPackage(course_id='test-dna',course_name='Evidence course',topics=[{'id':'t','name':'Limits','summary':'Limits'}],relationships=[],questions=qs)
    return course, {'s':{'session':ss[0],'questions':qs,'attempts':aa}}


def test_tag_review_creates_version_and_survives_json_restore():
    course,_=course_and_history()
    revised=review_question(course,'q0','approved',{'cognitive_dimension':'conceptual'})
    assert course.questions[0].cognitive_dimension=='computation'
    assert revised.questions[-1].version_of=='q0'
    restored=StudyPackage.model_validate_json(revised.model_dump_json())
    assert restored.questions[-1].cognitive_dimension=='conceptual'


@pytest.mark.parametrize('with_history',[False,True])
def test_progress_exposes_learning_dna_evidence(with_history):
    course,history=course_and_history()
    app=AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course']=course
    app.session_state['performance_mode_test-dna']='Topic Practice'
    if with_history: app.session_state['practice_history_test-dna']=history
    app.run()
    assert not app.exception
    assert 'Learning DNA' in [s.value for s in app.subheader]
    captions=' '.join(c.value for c in app.caption)
    assert 'not a validated cognitive diagnosis' in captions
    if with_history:
        assert 'Computation answers are more consistent' in ' '.join(m.value for m in app.markdown)
        assert len(next(frame.value for frame in app.dataframe if 'Dimension' in frame.value.columns))==6
    else:
        from tests.test_progress_charts import bar_rows, chart
        assert [row['value'] for row in bar_rows(chart(app,'dna'))]==['Not enough answers yet']*2
    app.radio(key='performance_mode_test-dna').set_value('Mock Exam').run()
    assert not app.exception
    assert not any("Dimension" in frame.value.columns for frame in app.dataframe)


def test_review_ui_can_tag_an_untagged_question_without_rewriting_history():
    course,_=course_and_history()
    course.questions[0].cognitive_dimension=None
    # Question review lives on the Course tools page.
    app=AppTest.from_file(str(ROOT/'pages/9_Course_Tools.py'))
    app.session_state['current_course']=course
    app.run()
    assert not app.exception
    dimension=next(s for s in app.radio if s.label=='Learning DNA evidence type')
    assert dimension.horizontal
    assert dimension.options==['Untagged','Computation','Conceptual understanding']
    assert dimension.value=='untagged'
    dimension.set_value('conceptual')
    next(b for b in app.button if b.label=='Save review').click().run()
    assert not app.exception
    saved=app.session_state['current_course']
    assert saved.questions[-1].cognitive_dimension=='conceptual'
    assert saved.questions[0].cognitive_dimension is None


@pytest.mark.parametrize('filename',['calculus_i_demo.json','sample_course.json','demo_python_basics.json'])
def test_demo_dimensions_do_not_approve_pending_questions(filename):
    from services.question_editor import available_questions
    course=StudyPackage.model_validate_json((ROOT/'data'/filename).read_text(encoding='utf-8'))
    assert {q.cognitive_dimension for q in course.questions}=={'computation','conceptual'}
    pending={qid for qid,status in course.learning_state['question_reviews'].items() if status=='pending'}
    assert pending.isdisjoint(q.id for q in available_questions(course))


def test_profile_uses_saved_chronology_on_progress_page():
    course,history=course_and_history()
    qs=course.questions
    later=ExamSession(session_id='later',mode='topic',question_ids=['q0'])
    # Reversed dict insertion order must not override saved chronological order.
    records={'later': {'session':later,'questions':[qs[0]],'attempts':[
        AttemptResult(session_id='later',question_id='q0',selected_index=1,is_correct=False)
    ]},**history}
    course.learning_state['session_order']=['s','later']
    app=AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course']=course
    app.session_state['performance_mode_test-dna']='Topic Practice'
    app.session_state['practice_history_test-dna']=records
    app.run()
    assert not app.exception
    from tests.test_progress_charts import bar_rows, chart
    computation=bar_rows(chart(app,'dna'))[0]
    assert computation['label']=='Computation' and computation['value']=='67%'


def test_progress_for_old_untagged_history_does_not_infer_abilities():
    course,history=course_and_history()
    for q in course.questions: q.cognitive_dimension=None
    app=AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course']=course
    app.session_state['practice_history_test-dna']=history
    app.session_state['performance_mode_test-dna']='Topic Practice'
    app.run()
    assert not app.exception
    assert 'excluded' not in ' '.join(c.value for c in app.caption)
    assert not any("Dimension" in frame.value.columns for frame in app.dataframe)
    from tests.test_progress_charts import bar_rows, chart
    computation=bar_rows(chart(app,'dna'))[0]
    assert computation['label']=='Computation' and computation['value']=='Not enough answers yet'
    assert computation['fill'] is None and computation['detail']=='0 different questions'


def test_dashboard_entry_navigates_to_learning_dna_in_registered_app():
    from tests.auth_helpers import signed_in_app
    app=signed_in_app(ROOT/'app.py').run()
    assert not app.exception
    assert app.button(key='learning_dna_open').disabled
    course,history=course_and_history()
    app.session_state['current_course']=course
    app.session_state['practice_history_test-dna']=history
    app.session_state['performance_mode_test-dna']='Topic Practice'
    app.run()
    app.button(key='learning_dna_open').click().run()
    assert not app.exception
    assert app.title[0].value=='Progress'
    assert 'Learning DNA' in [s.value for s in app.subheader]
