"""Explicit append-only demo updates; never replace a learner's saved questions."""
from pathlib import Path
from copy import deepcopy
from models.schemas import StudyPackage
from services.question_review import normalized_text

FILES={'calculus-i-demo':'calculus_i_demo.json','econ101':'sample_course.json','python-basics-demo':'demo_python_basics.json'}


def demo_update(course):
    filename=FILES.get(course.course_id)
    if not filename:return course,0
    latest=StudyPackage.model_validate_json((Path(__file__).resolve().parents[1]/'data'/filename).read_text(encoding='utf-8'))
    known={q.id for q in course.questions}
    stems={normalized_text(q.question) for q in course.questions}
    topics={t.id for t in course.topics}
    added=[q for q in latest.questions if q.id not in known and q.topic_id in topics and normalized_text(q.question) not in stems]
    if not added:return course,0
    data=course.model_dump(mode='json')
    data['questions'].extend(q.model_dump(mode='json') for q in added)
    metadata=deepcopy(course.learning_state)
    reviews=metadata.setdefault('question_reviews',{})
    for q in added:reviews[q.id]='pending'
    data['learning_state']=metadata
    return StudyPackage.model_validate(data),len(added)
