import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from google.genai.errors import APIError

from models.schemas import Question, Relationship, StudyPackage, Topic
from services import gemini_service


FAKE_API_KEY = "test-gemini-key-never-real"
PROMPT = "Reply with only: ExamPilot API OK"


def make_topics(*, source_pages=None, count=3, duplicate_ids=False):
    topics = []
    for index in range(count):
        topic_id = "duplicate" if duplicate_ids else f"topic-{index + 1}"
        topics.append(
            {
                "id": topic_id,
                "name": f"Knowledge area {index + 1}",
                "summary": f"Supported summary {index + 1}.",
                "source_pages": list(source_pages or []),
            }
        )
    return topics


def make_txt_document(text="Course material for analysis."):
    return {
        "ok": True,
        "filename": "course.txt",
        "text": text,
        "sources": [{"filename": "course.txt", "page": None}],
    }


def make_pdf_document():
    pages = [
        {"page": 2, "text": "First extractable page."},
        {"page": 3, "text": ""},
        {"page": 4, "text": "Second extractable page."},
    ]
    return {
        "ok": True,
        "filename": "course.pdf",
        "text": "\n".join(page["text"] for page in pages),
        "pages": pages,
        "sources": [
            {"filename": "course.pdf", "page": 2},
            {"filename": "course.pdf", "page": 4},
        ],
    }


def make_study_package():
    return StudyPackage(
        course_id="course-1",
        course_name="General Studies",
        topics=[
            Topic(
                id=f"topic-{index}",
                name=f"Knowledge area {index}",
                summary=f"Supported summary {index}.",
                source_pages=[],
            )
            for index in range(1, 4)
        ],
        relationships=[
            Relationship(
                from_topic="topic-1",
                to_topic="topic-2",
                type="related",
            )
        ],
        questions=[
            Question(
                id="existing-question",
                topic_id="topic-1",
                question="Existing question?",
                options=["A", "B", "C", "D"],
                correct_index=0,
                explanation="Existing explanation.",
                source_pages=[],
            )
        ],
    )


def make_questions(
    *,
    count=8,
    topic_id="topic-1",
    source_pages=None,
    duplicate_ids=False,
    options=None,
    correct_index=1,
):
    questions = []
    for index in range(count):
        questions.append(
            {
                "id": "duplicate" if duplicate_ids else f"question-{index + 1}",
                "topic_id": topic_id,
                "question": f"Question {index + 1}?",
                "options": list(options or ["Alpha", "Bravo", "Charlie", "Delta"]),
                "correct_index": correct_index,
                "explanation": f"Explanation {index + 1}.",
                "source_pages": list(source_pages or []),
            }
        )
    return questions


def make_relationships(edges=None):
    if edges is None:
        edges = [("topic-1", "topic-2", "related")]
    return [
        {
            "from_topic": from_topic,
            "to_topic": to_topic,
            "type": relationship_type,
        }
        for from_topic, to_topic, relationship_type in edges
    ]


def install_fake_client(monkeypatch, *, text=None, error=None):
    clients = []

    class FakeModels:
        def __init__(self):
            self.calls = []
            self.configs = []

        def generate_content(self, *, model, contents, config=None):
            self.calls.append({"model": model, "contents": contents})
            self.configs.append(config)
            if error is not None:
                raise error
            return SimpleNamespace(text=text)

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.models = FakeModels()
            self.exited = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.exited = True
            return False

    def client_factory(*, api_key):
        client = FakeClient(api_key=api_key)
        clients.append(client)
        return client

    monkeypatch.setattr(gemini_service.genai, "Client", client_factory)
    return clients


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_missing_or_blank_api_key_does_not_create_client(monkeypatch, api_key):
    if api_key is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", api_key)

    def fail_if_client_created(**kwargs):
        pytest.fail("Client must not be created without a non-blank API key")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.check_gemini_connection()

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_API_KEY"


def test_success_uses_default_model_prompt_and_exits_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    clients = install_fake_client(monkeypatch, text="ExamPilot API OK")

    result = gemini_service.check_gemini_connection()

    assert result == {
        "ok": True,
        "model": "gemini-3.8-flash",
        "text": "ExamPilot API OK",
    }
    assert len(clients) == 1
    assert clients[0].api_key == FAKE_API_KEY
    assert clients[0].models.calls == [
        {"model": "gemini-3.8-flash", "contents": PROMPT}
    ]
    assert clients[0].exited is True


def test_custom_model_is_passed_to_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "exam-pilot-test-model")
    clients = install_fake_client(monkeypatch, text="ready")

    result = gemini_service.check_gemini_connection()

    assert result["ok"] is True
    assert result["model"] == "exam-pilot-test-model"
    assert clients[0].models.calls == [
        {"model": "exam-pilot-test-model", "contents": PROMPT}
    ]


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_response_returns_empty_response_error(monkeypatch, text):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    clients = install_fake_client(monkeypatch, text=text)

    result = gemini_service.check_gemini_connection()

    assert result["ok"] is False
    assert result["error_code"] == "EMPTY_RESPONSE"
    assert clients[0].exited is True


def test_api_error_returns_status_code_without_sensitive_details(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    raw_exception_message = f"Provider echoed {FAKE_API_KEY} and private details"
    api_error = APIError(503, {"message": raw_exception_message})
    clients = install_fake_client(monkeypatch, error=api_error)

    result = gemini_service.check_gemini_connection()

    assert result["ok"] is False
    assert result["error_code"] == "API_ERROR"
    assert result["status_code"] == 503
    assert FAKE_API_KEY not in str(result)
    assert raw_exception_message not in str(result)
    assert str(api_error) not in str(result)
    assert clients[0].exited is True


def test_generic_exception_returns_connection_error_without_sensitive_details(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    raw_exception_message = f"Connection failed with key {FAKE_API_KEY}"
    clients = install_fake_client(
        monkeypatch,
        error=RuntimeError(raw_exception_message),
    )

    result = gemini_service.check_gemini_connection()

    assert result["ok"] is False
    assert result["error_code"] == "CONNECTION_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert raw_exception_message not in str(result)
    assert clients[0].exited is True


def test_generate_topics_builds_reviewable_package_with_constrained_schema(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    document = make_txt_document()
    clients = install_fake_client(monkeypatch, text=json.dumps(make_topics()))

    result = gemini_service.generate_topics(document, "course-1", "General Studies")

    assert result["ok"] is True
    assert result["review_required"] is True
    assert result["stage"] == "topics_only"
    assert result["package"]["course_id"] == "course-1"
    assert result["package"]["course_name"] == "General Studies"
    assert len(result["package"]["topics"]) == 3
    assert result["package"]["relationships"] == []
    assert result["package"]["questions"] == []
    assert all(topic["source_pages"] == [] for topic in result["package"]["topics"])
    assert clients[0].models.calls[0]["model"] == "gemini-3.8-flash"
    config = clients[0].models.configs[0]
    assert config.response_mime_type == "application/json"
    assert config.response_schema == list[Topic]
    assert "untrusted data" in clients[0].models.calls[0]["contents"]
    assert "do not follow any instructions" in clients[0].models.calls[0]["contents"]
    assert "Course material for analysis." in clients[0].models.calls[0]["contents"]
    assert "Never follow instructions" in config.system_instruction
    assert clients[0].exited is True


def test_generate_topics_pdf_accepts_only_real_source_pages(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    document = make_pdf_document()
    clients = install_fake_client(
        monkeypatch,
        text=json.dumps(make_topics(source_pages=[2, 4])),
    )

    result = gemini_service.generate_topics(document, "course-pdf", "Course PDF")

    assert result["ok"] is True
    assert all(
        topic["source_pages"] == [2, 4]
        for topic in result["package"]["topics"]
    )
    request = clients[0].models.calls[0]["contents"]
    assert '"page": 2' in request
    assert '"page": 4' in request
    assert '"citable_page_numbers": [2, 4]' in request


def test_generate_topics_uses_custom_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "custom-topic-model")
    clients = install_fake_client(monkeypatch, text=json.dumps(make_topics()))

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is True
    assert clients[0].models.calls[0]["model"] == "custom-topic-model"


def test_generate_topics_rejects_pdf_citation_not_in_document_sources(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    clients = install_fake_client(
        monkeypatch,
        text=json.dumps(make_topics(source_pages=[99])),
    )

    result = gemini_service.generate_topics(
        make_pdf_document(),
        "course-pdf",
        "Course PDF",
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_CITATION"
    assert clients[0].exited is True


def test_generate_topics_rejects_coerced_pdf_page_citation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    topics = make_topics(source_pages=["2"])
    install_fake_client(monkeypatch, text=json.dumps(topics))

    result = gemini_service.generate_topics(
        make_pdf_document(),
        "course-pdf",
        "Course PDF",
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_TOPICS"


def test_generate_topics_rejects_duplicate_topic_ids(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_topics(duplicate_ids=True)),
    )

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_TOPICS"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [("id", " "), ("name", ""), ("summary", " \t")],
)
def test_generate_topics_rejects_blank_topic_fields(
    monkeypatch,
    field,
    invalid_value,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    topics = make_topics()
    topics[0][field] = invalid_value
    install_fake_client(monkeypatch, text=json.dumps(topics))

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_TOPICS"


@pytest.mark.parametrize(
    ("count", "expected_error"),
    [(2, "INSUFFICIENT_CONTENT"), (6, "INVALID_TOPICS")],
)
def test_generate_topics_rejects_topic_count_outside_range(
    monkeypatch,
    count,
    expected_error,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text=json.dumps(make_topics(count=count)))

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == expected_error


def test_generate_topics_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text="{not valid json}")

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_JSON"


def test_generate_topics_rejects_empty_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text="  ")

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "EMPTY_RESPONSE"


@pytest.mark.parametrize(
    ("document", "course_id", "course_name", "error_code"),
    [
        ({"ok": False}, "course-1", "Course", "INVALID_DOCUMENT"),
        (make_txt_document("  "), "course-1", "Course", "EMPTY_DOCUMENT"),
        (
            make_txt_document("x" * 50_001),
            "course-1",
            "Course",
            "TEXT_TOO_LONG",
        ),
        (make_txt_document(), "  ", "Course", "INVALID_COURSE_METADATA"),
        (make_txt_document(), "course-1", "", "INVALID_COURSE_METADATA"),
    ],
)
def test_generate_topics_invalid_input_does_not_create_client(
    monkeypatch,
    document,
    course_id,
    course_name,
    error_code,
):
    def fail_if_client_created(**kwargs):
        pytest.fail("Invalid input must be rejected before creating the client")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_topics(document, course_id, course_name)

    assert result["ok"] is False
    assert result["error_code"] == error_code


def test_generate_topics_missing_api_key_does_not_create_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_if_client_created(**kwargs):
        pytest.fail("Client must not be created without an API key")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_API_KEY"


def test_generate_topics_api_error_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course content"
    install_fake_client(
        monkeypatch,
        error=APIError(503, {"message": private_message}),
    )

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "API_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)


def test_generate_topics_generic_error_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course content"
    install_fake_client(monkeypatch, error=RuntimeError(private_message))

    result = gemini_service.generate_topics(make_txt_document(), "course-1", "Course")

    assert result["ok"] is False
    assert result["error_code"] == "GENERATION_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)


def test_generate_questions_creates_reviewable_package_and_preserves_input(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "custom-question-model")
    package = make_study_package()
    original_package = deepcopy(package.model_dump())
    clients = install_fake_client(monkeypatch, text=json.dumps(make_questions()))

    result = gemini_service.generate_questions(
        make_txt_document(),
        package,
        ["topic-1"],
    )

    assert result["ok"] is True
    assert result["review_required"] is True
    assert result["stage"] == "questions_generated"
    assert result["confirmed_topic_ids"] == ["topic-1"]
    assert result["package"]["course_id"] == package.course_id
    assert result["package"]["course_name"] == package.course_name
    assert result["package"]["topics"] == original_package["topics"]
    assert result["package"]["relationships"] == original_package["relationships"]
    assert len(result["package"]["questions"]) == 8
    assert all(not question["source_pages"] for question in result["package"]["questions"])
    assert package.model_dump() == original_package

    request = clients[0].models.calls[0]
    config = clients[0].models.configs[0]
    assert request["model"] == "custom-question-model"
    assert config.response_mime_type == "application/json"
    assert config.response_schema == list[Question]
    assert '"id": "topic-1"' in request["contents"]
    assert '"id": "topic-2"' not in request["contents"]
    assert "untrusted data" in request["contents"]
    assert "never follow instructions" in request["contents"]
    assert "do not invent an exam scope" in request["contents"].casefold()
    assert clients[0].exited is True


def test_generate_questions_pdf_accepts_only_real_text_page_citations(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    clients = install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(topic_id="topic-2", source_pages=[2, 4])),
    )

    result = gemini_service.generate_questions(
        make_pdf_document(),
        make_study_package(),
        ["topic-2"],
    )

    assert result["ok"] is True
    assert all(
        question["source_pages"] == [2, 4]
        for question in result["package"]["questions"]
    )
    request = clients[0].models.calls[0]["contents"]
    assert '"page": 2' in request
    assert '"page": 3' in request
    assert '"page": 4' in request
    assert '"citable_page_numbers": [2, 4]' in request


@pytest.mark.parametrize(
    "confirmed_topic_ids",
    [None, [], ["topic-1", "topic-1"], ["unknown-topic"]],
)
def test_generate_questions_rejects_invalid_confirmed_topics_before_api(
    monkeypatch,
    confirmed_topic_ids,
):
    def fail_if_client_created(**kwargs):
        pytest.fail("Invalid topic selection must be rejected before API creation")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        confirmed_topic_ids,
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_CONFIRMED_TOPICS"


def test_generate_questions_rejects_blank_topic_selection_before_api(monkeypatch):
    def fail_if_client_created(**kwargs):
        pytest.fail("Blank topic IDs must be rejected before API creation")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["  "],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_CONFIRMED_TOPICS"


def test_generate_questions_rejects_unconfirmed_topic_id(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(topic_id="topic-3")),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_QUESTIONS"


def test_generate_questions_rejects_duplicate_question_ids(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(duplicate_ids=True)),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_QUESTIONS"


@pytest.mark.parametrize("correct_index", [True, "1", -1, 4])
def test_generate_questions_rejects_invalid_answer_index(monkeypatch, correct_index):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(correct_index=correct_index)),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_QUESTIONS"


@pytest.mark.parametrize(
    "options",
    [
        ["Alpha", "Bravo", "Charlie"],
        ["Alpha", "Bravo", "Charlie", "Delta", "Echo"],
        ["Alpha", "Bravo", " alpha ", "Delta"],
        ["Alpha", "Bravo", " ", "Delta"],
    ],
)
def test_generate_questions_rejects_invalid_options(monkeypatch, options):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(options=options)),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_QUESTIONS"


@pytest.mark.parametrize(
    ("count", "error_code"),
    [(7, "INSUFFICIENT_CONTENT"), (13, "INVALID_QUESTIONS")],
)
def test_generate_questions_rejects_invalid_question_count(
    monkeypatch,
    count,
    error_code,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text=json.dumps(make_questions(count=count)))

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == error_code


def test_generate_questions_rejects_invalid_pdf_citation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(source_pages=[99])),
    )

    result = gemini_service.generate_questions(
        make_pdf_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_CITATION"


def test_generate_questions_rejects_txt_page_citation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_questions(source_pages=[1])),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_CITATION"


def test_generate_questions_api_error_is_safe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course material"
    install_fake_client(
        monkeypatch,
        error=APIError(503, {"message": private_message}),
    )

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "API_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)


def test_generate_questions_connection_error_is_safe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course material"
    install_fake_client(monkeypatch, error=RuntimeError(private_message))

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "GENERATION_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)


@pytest.mark.parametrize(
    ("document", "package", "expected_error"),
    [
        ({"ok": False}, make_study_package(), "INVALID_DOCUMENT"),
        (
            make_txt_document("x" * 50_001),
            make_study_package(),
            "TEXT_TOO_LONG",
        ),
        (make_txt_document(), {}, "INVALID_PACKAGE"),
    ],
)
def test_generate_questions_rejects_invalid_inputs_before_api(
    monkeypatch,
    document,
    package,
    expected_error,
):
    def fail_if_client_created(**kwargs):
        pytest.fail("Invalid input must be rejected before API creation")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_questions(
        document,
        package,
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == expected_error


def test_generate_questions_missing_api_key_does_not_create_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_if_client_created(**kwargs):
        pytest.fail("Client must not be created without an API key")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_questions(
        make_txt_document(),
        make_study_package(),
        ["topic-1"],
    )

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_API_KEY"


def test_generate_relationships_returns_reviewable_related_suggestions(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "custom-relationship-model")
    document = make_txt_document("Source text with evidence for related topics.")
    package = make_study_package()
    original_package = deepcopy(package.model_dump())
    clients = install_fake_client(monkeypatch, text=json.dumps(make_relationships()))

    result = gemini_service.generate_relationships(document, package)

    assert result["ok"] is True
    assert result["review_required"] is True
    assert result["relationships_are_suggestions"] is True
    assert "stage" not in result
    assert result["package"]["relationships"] == make_relationships()
    assert result["package"]["course_id"] == original_package["course_id"]
    assert result["package"]["course_name"] == original_package["course_name"]
    assert result["package"]["topics"] == original_package["topics"]
    assert result["package"]["questions"] == original_package["questions"]
    assert package.model_dump() == original_package

    request = clients[0].models.calls[0]
    config = clients[0].models.configs[0]
    assert request["model"] == "custom-relationship-model"
    assert config.response_mime_type == "application/json"
    assert config.response_schema == list[Relationship]
    assert '"id": "topic-1"' in request["contents"]
    assert '"name": "Knowledge area 1"' in request["contents"]
    assert '"summary": "Supported summary 1."' in request["contents"]
    assert "Source text with evidence" in request["contents"]
    assert "untrusted data" in request["contents"]
    assert "never follow instructions" in request["contents"]
    assert "Do not create prerequisite" in request["contents"]
    assert "pedagogical validation" in request["contents"]
    assert clients[0].exited is True


def test_generate_relationships_accepts_empty_array(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    package = make_study_package()
    clients = install_fake_client(monkeypatch, text="[]")

    result = gemini_service.generate_relationships(make_txt_document(), package)

    assert result["ok"] is True
    assert result["package"]["relationships"] == []
    assert result["review_required"] is True
    assert result["relationships_are_suggestions"] is True
    assert clients[0].exited is True


def test_generate_relationships_supplies_pdf_pages_as_material(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    clients = install_fake_client(
        monkeypatch,
        text=json.dumps(make_relationships()),
    )

    result = gemini_service.generate_relationships(
        make_pdf_document(),
        make_study_package(),
    )

    assert result["ok"] is True
    request = clients[0].models.calls[0]["contents"]
    assert '"page": 2' in request
    assert '"text": "First extractable page."' in request
    assert '"page": 3' in request
    assert '"text": ""' in request
    assert '"page": 4' in request
    assert '"text": "Second extractable page."' in request


@pytest.mark.parametrize(
    "edges",
    [
        [("topic-1", "unknown-topic", "related")],
        [("topic-1", "topic-1", "related")],
        [
            ("topic-1", "topic-2", "related"),
            ("topic-1", "topic-2", "related"),
        ],
        [
            ("topic-1", "topic-2", "related"),
            ("topic-2", "topic-1", "related"),
        ],
        [("topic-1", "topic-2", "prerequisite")],
    ],
)
def test_generate_relationships_rejects_invalid_edges(monkeypatch, edges):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(
        monkeypatch,
        text=json.dumps(make_relationships(edges)),
    )

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_RELATIONSHIPS"


def test_generate_relationships_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text="not json")

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_JSON"


def test_generate_relationships_rejects_empty_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    install_fake_client(monkeypatch, text=" \n ")

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "EMPTY_RESPONSE"


@pytest.mark.parametrize(
    ("document", "package", "error_code"),
    [
        ({"ok": False}, make_study_package(), "INVALID_DOCUMENT"),
        (
            {**make_txt_document(), "text": "  "},
            make_study_package(),
            "EMPTY_DOCUMENT",
        ),
        (
            {**make_txt_document(), "text": "x" * 50_001},
            make_study_package(),
            "TEXT_TOO_LONG",
        ),
        (make_txt_document(), {}, "INVALID_PACKAGE"),
        (
            make_txt_document(),
            StudyPackage(
                course_id="course-1",
                course_name="General Studies",
                topics=[make_study_package().topics[0]],
                relationships=[],
                questions=[],
            ),
            "INSUFFICIENT_TOPICS",
        ),
    ],
)
def test_generate_relationships_rejects_invalid_input_before_api(
    monkeypatch,
    document,
    package,
    error_code,
):
    def fail_if_client_created(**kwargs):
        pytest.fail("Invalid input must be rejected before API creation")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_relationships(document, package)

    assert result["ok"] is False
    assert result["error_code"] == error_code


def test_generate_relationships_missing_api_key_does_not_create_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_if_client_created(**kwargs):
        pytest.fail("Client must not be created without an API key")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_client_created)

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_API_KEY"


def test_generate_relationships_api_error_does_not_expose_sensitive_data(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course material"
    install_fake_client(
        monkeypatch,
        error=APIError(503, {"message": private_message}),
    )

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "API_ERROR"
    assert result["status_code"] == 503
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)


def test_generate_relationships_connection_error_is_safe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    private_message = f"{FAKE_API_KEY} private course material"
    install_fake_client(monkeypatch, error=RuntimeError(private_message))

    result = gemini_service.generate_relationships(
        make_txt_document(),
        make_study_package(),
    )

    assert result["ok"] is False
    assert result["error_code"] == "GENERATION_ERROR"
    assert FAKE_API_KEY not in str(result)
    assert private_message not in str(result)