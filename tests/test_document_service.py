import pytest

from services.document_service import (
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    extract_txt,
)


@pytest.mark.parametrize(
    ("text", "filename"),
    [
        ("Plain UTF-8 text", "notes.txt"),
        ("中文内容", "课程资料.txt"),
        ("BOM-prefixed text", "bom.txt"),
        ("Uppercase extension", "NOTES.TXT"),
    ],
)
def test_extract_txt_success_and_page_is_none(text, filename):
    file_bytes = text.encode("utf-8-sig") if filename == "bom.txt" else text.encode("utf-8")

    result = extract_txt(file_bytes, filename)

    assert result == {
        "ok": True,
        "filename": filename,
        "text": text,
        "sources": [{"filename": filename, "page": None}],
    }


def test_rejects_non_txt_extension():
    result = extract_txt(b"text", "notes.pdf")

    assert result["ok"] is False
    assert result["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.parametrize("file_bytes", [b"", b" \t\r\n"])
def test_rejects_empty_content(file_bytes):
    result = extract_txt(file_bytes, "empty.txt")

    assert result["ok"] is False
    assert result["error_code"] == "EMPTY_DOCUMENT"


def test_rejects_invalid_utf8():
    result = extract_txt(b"valid prefix\xffinvalid", "invalid.txt")

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_ENCODING"


def test_file_size_limit_accepts_exact_boundary_before_text_limit():
    file_bytes = b"a" * MAX_FILE_BYTES

    result = extract_txt(file_bytes, "at-size-limit.txt")

    assert result["ok"] is False
    assert result["error_code"] == "TEXT_TOO_LONG"


def test_rejects_file_over_size_limit():
    file_bytes = b"a" * (MAX_FILE_BYTES + 1)

    result = extract_txt(file_bytes, "over-size-limit.txt")

    assert result["ok"] is False
    assert result["error_code"] == "FILE_TOO_LARGE"


def test_text_length_limit_accepts_exact_boundary():
    text = "a" * MAX_TEXT_CHARS

    result = extract_txt(text.encode("utf-8"), "at-text-limit.txt")

    assert result["ok"] is True
    assert result["text"] == text
    assert result["sources"] == [{"filename": "at-text-limit.txt", "page": None}]


def test_rejects_text_over_length_limit():
    text = "a" * (MAX_TEXT_CHARS + 1)

    result = extract_txt(text.encode("utf-8"), "over-text-limit.txt")

    assert result["ok"] is False
    assert result["error_code"] == "TEXT_TOO_LONG"