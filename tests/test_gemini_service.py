from types import SimpleNamespace

import pytest
from google.genai.errors import APIError

from services import gemini_service


FAKE_API_KEY = "test-gemini-key-never-real"
PROMPT = "Reply with only: ExamPilot API OK"


def install_fake_client(monkeypatch, *, text=None, error=None):
    clients = []

    class FakeModels:
        def __init__(self):
            self.calls = []

        def generate_content(self, *, model, contents):
            self.calls.append({"model": model, "contents": contents})
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