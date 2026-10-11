from io import BytesIO

import pytest
import pymupdf
from PIL import Image
from pptx import Presentation
from pptx.oxml.xmlchemy import OxmlElement

from services import document_service, gemini_service
from services.document_service import (
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    extract_image,
    extract_pdf,
    extract_pptx,
    extract_txt,
)


class FakeTesseractNotFoundError(OSError):
    pass


class FakeTesseractError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def make_image_bytes(image_format="PNG"):
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(stream, format=image_format)
    return stream.getvalue()


def install_fake_ocr(
    monkeypatch,
    *,
    text="Recognized image text",
    languages=("eng",),
    languages_error=None,
    ocr_error=None,
):
    calls = []

    class FakePytesseract:
        TesseractError = FakeTesseractError
        TesseractNotFoundError = FakeTesseractNotFoundError

        def get_languages(self, *, config):
            if languages_error is not None:
                raise languages_error
            return list(languages)

        def image_to_string(self, image, *, lang, timeout):
            calls.append((image, lang, timeout))
            if ocr_error is not None:
                raise ocr_error
            return text

    fake_pytesseract = FakePytesseract()
    monkeypatch.setattr(
        document_service,
        "_load_pytesseract",
        lambda: fake_pytesseract,
        raising=False,
    )
    return calls


def make_pdf(page_texts, *, user_password=None):
    document = pymupdf.open()
    for page_text in page_texts:
        page = document.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)

    options = {}
    if user_password is not None:
        options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "test-owner-password",
            "user_pw": user_password,
        }

    file_bytes = document.tobytes(**options)
    document.close()
    return file_bytes


def add_grouped_text(slide, text):
    shape = slide.shapes.add_textbox(0, 0, 1_000_000, 300_000)
    shape.text_frame.text = text
    shape_element = shape._element
    shape_parent = shape_element.getparent()

    group = OxmlElement("p:grpSp")
    nonvisual = OxmlElement("p:nvGrpSpPr")
    nonvisual_shape = OxmlElement("p:cNvPr")
    nonvisual_shape.set("id", "99")
    nonvisual_shape.set("name", "Test Group")
    nonvisual.append(nonvisual_shape)
    nonvisual.append(OxmlElement("p:cNvGrpSpPr"))
    nonvisual.append(OxmlElement("p:nvPr"))
    group.append(nonvisual)

    group_properties = OxmlElement("p:grpSpPr")
    transform = OxmlElement("a:xfrm")
    for tag, attributes in (
        ("a:off", {"x": "0", "y": "0"}),
        ("a:ext", {"cx": "1000000", "cy": "300000"}),
        ("a:chOff", {"x": "0", "y": "0"}),
        ("a:chExt", {"cx": "1000000", "cy": "300000"}),
    ):
        element = OxmlElement(tag)
        for key, value in attributes.items():
            element.set(key, value)
        transform.append(element)
    group_properties.append(transform)
    group.append(group_properties)

    shape_parent.remove(shape_element)
    group.append(shape_element)
    slide.shapes._spTree.insert_element_before(group, "p:extLst")


def make_pptx(slide_specs):
    presentation = Presentation()
    for spec in slide_specs:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        for item in spec:
            if item[0] == "text":
                shape = slide.shapes.add_textbox(0, 0, 1_000_000, 300_000)
                shape.text_frame.text = item[1]
            elif item[0] == "table":
                table = slide.shapes.add_table(
                    len(item[1]),
                    len(item[1][0]),
                    0,
                    0,
                    2_000_000,
                    1_000_000,
                ).table
                for row_index, row in enumerate(item[1]):
                    for column_index, value in enumerate(row):
                        table.cell(row_index, column_index).text = value
            elif item[0] == "group":
                add_grouped_text(slide, item[1])

    stream = BytesIO()
    presentation.save(stream)
    return stream.getvalue()


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


def test_extract_pdf_returns_page_text_and_real_page_sources():
    file_bytes = make_pdf(["First page", "Second page"])

    result = extract_pdf(file_bytes, "course.pdf")

    assert result["ok"] is True
    assert result["filename"] == "course.pdf"
    assert [page["page"] for page in result["pages"]] == [1, 2]
    assert [page["text"].strip() for page in result["pages"]] == [
        "First page",
        "Second page",
    ]
    assert result["text"] == "\n".join(page["text"] for page in result["pages"])
    assert result["sources"] == [
        {"filename": "course.pdf", "page": 1},
        {"filename": "course.pdf", "page": 2},
    ]


def test_extract_pdf_retains_blank_pages_but_omits_them_from_sources():
    file_bytes = make_pdf(["First page", "", "Third page"])

    result = extract_pdf(file_bytes, "mixed.pdf")

    assert result["ok"] is True
    assert [page["page"] for page in result["pages"]] == [1, 2, 3]
    assert result["pages"][1]["text"] == ""
    assert result["sources"] == [
        {"filename": "mixed.pdf", "page": 1},
        {"filename": "mixed.pdf", "page": 3},
    ]


def test_extract_pdf_accepts_uppercase_extension():
    result = extract_pdf(make_pdf(["Text"]), "COURSE.PDF")

    assert result["ok"] is True
    assert result["filename"] == "COURSE.PDF"


def test_extract_pdf_rejects_pdf_without_extractable_text():
    result = extract_pdf(make_pdf(["", " \t "]), "blank.pdf")

    assert result["ok"] is False
    assert result["error_code"] == "NO_EXTRACTABLE_TEXT"
    assert "OCR" in result["message"]


def test_extract_pdf_rejects_corrupt_content_without_exposing_exception():
    result = extract_pdf(b"not a PDF document", "corrupt.pdf")

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_PDF"
    assert "not a PDF document" not in result["message"]


def test_extract_pdf_rejects_empty_bytes():
    result = extract_pdf(b"", "empty.pdf")

    assert result["ok"] is False
    assert result["error_code"] == "EMPTY_DOCUMENT"


def test_extract_pdf_rejects_encrypted_document():
    file_bytes = make_pdf(["Secret text"], user_password="test-user-password")

    result = extract_pdf(file_bytes, "encrypted.pdf")

    assert result["ok"] is False
    assert result["error_code"] == "ENCRYPTED_PDF"


def test_extract_pdf_rejects_unsupported_file_type():
    result = extract_pdf(make_pdf(["Text"]), "course.txt")

    assert result["ok"] is False
    assert result["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_extract_pdf_file_size_limit(monkeypatch):
    file_bytes = make_pdf(["Small PDF"])
    monkeypatch.setattr(document_service, "MAX_FILE_BYTES", len(file_bytes))

    at_limit_result = extract_pdf(file_bytes, "at-limit.pdf")
    over_limit_result = extract_pdf(file_bytes + b"x", "over-limit.pdf")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "FILE_TOO_LARGE"


def test_extract_pdf_text_length_limit(monkeypatch):
    file_bytes = make_pdf(["Text length boundary"])
    initial_result = extract_pdf(file_bytes, "text-limit.pdf")
    assert initial_result["ok"] is True
    monkeypatch.setattr(
        document_service,
        "MAX_TEXT_CHARS",
        len(initial_result["text"]),
    )

    at_limit_result = extract_pdf(file_bytes, "text-limit.pdf")
    monkeypatch.setattr(
        document_service,
        "MAX_TEXT_CHARS",
        len(initial_result["text"]) - 1,
    )
    over_limit_result = extract_pdf(file_bytes, "text-limit.pdf")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "TEXT_TOO_LONG"


def test_extract_pptx_extracts_text_table_group_and_blank_slides():
    file_bytes = make_pptx(
        [
            [
                ("text", "Slide title"),
                ("table", [["Name", "Value"], ["count", "3"]]),
                ("group", "Grouped text"),
            ],
            [],
            [("text", "Final slide")],
        ]
    )

    result = extract_pptx(file_bytes, "course.pptx")

    assert result["ok"] is True
    assert result["filename"] == "course.pptx"
    assert [page["page"] for page in result["pages"]] == [1, 2, 3]
    assert "Slide title" in result["pages"][0]["text"]
    assert "Name\tValue" in result["pages"][0]["text"]
    assert "count\t3" in result["pages"][0]["text"]
    assert "Grouped text" in result["pages"][0]["text"]
    assert result["pages"][1]["text"] == ""
    assert result["pages"][2]["text"] == "Final slide"
    assert result["text"] == "\n".join(page["text"] for page in result["pages"])
    assert result["sources"] == [
        {"filename": "course.pptx", "page": 1},
        {"filename": "course.pptx", "page": 3},
    ]


def test_extract_pptx_accepts_uppercase_extension_and_dispatches():
    file_bytes = make_pptx([[('text', 'Uppercase extension')]])

    result = document_service.extract_document(file_bytes, "COURSE.PPTX")

    assert result["ok"] is True
    assert result["filename"] == "COURSE.PPTX"
    assert result["sources"] == [{"filename": "COURSE.PPTX", "page": 1}]


@pytest.mark.parametrize("file_bytes", [b"", b"not a presentation"])
def test_extract_pptx_rejects_empty_or_corrupt_content(file_bytes):
    result = extract_pptx(file_bytes, "invalid.pptx")

    assert result["ok"] is False
    assert result["error_code"] == (
        "EMPTY_DOCUMENT" if not file_bytes else "INVALID_PPTX"
    )
    assert "not a presentation" not in result["message"]


def test_extract_pptx_rejects_presentation_without_text():
    result = extract_pptx(make_pptx([[], []]), "blank.pptx")

    assert result["ok"] is False
    assert result["error_code"] == "NO_EXTRACTABLE_TEXT"
    assert "OCR" in result["message"]


def test_extract_pptx_rejects_unsupported_extension():
    result = extract_pptx(make_pptx([[('text', 'Text')]]), "slides.ppt")

    assert result["ok"] is False
    assert result["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_extract_pptx_file_size_limit(monkeypatch):
    file_bytes = make_pptx([[('text', 'File size limit')]])
    monkeypatch.setattr(document_service, "MAX_FILE_BYTES", len(file_bytes))

    at_limit_result = extract_pptx(file_bytes, "at-limit.pptx")
    over_limit_result = extract_pptx(file_bytes + b"x", "over-limit.pptx")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "FILE_TOO_LARGE"


def test_extract_pptx_text_length_limit(monkeypatch):
    file_bytes = make_pptx([[('text', 'PPTX length boundary')]])
    initial_result = extract_pptx(file_bytes, "text-limit.pptx")
    assert initial_result["ok"] is True
    text_length = len(initial_result["text"])
    monkeypatch.setattr(document_service, "MAX_TEXT_CHARS", text_length)

    at_limit_result = extract_pptx(file_bytes, "text-limit.pptx")
    monkeypatch.setattr(document_service, "MAX_TEXT_CHARS", text_length - 1)
    over_limit_result = extract_pptx(file_bytes, "text-limit.pptx")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "TEXT_TOO_LONG"


@pytest.mark.parametrize(
    ("image_format", "filename"),
    [("PNG", "course.png"), ("JPEG", "course.JPG"), ("JPEG", "course.jpeg")],
)
def test_extract_image_returns_virtual_page_one_and_uses_local_ocr(
    monkeypatch,
    image_format,
    filename,
):
    monkeypatch.delenv("OCR_LANG", raising=False)
    calls = install_fake_ocr(monkeypatch)

    result = extract_image(make_image_bytes(image_format), filename)

    assert result == {
        "ok": True,
        "filename": filename,
        "text": "Recognized image text",
        "pages": [{"page": 1, "text": "Recognized image text"}],
        "sources": [{"filename": filename, "page": 1}],
    }
    assert len(calls) == 1
    assert calls[0][0].mode == "RGB"
    assert calls[0][1:] == ("eng", 15)


def test_extract_image_uses_configured_language_pack(monkeypatch):
    monkeypatch.setenv("OCR_LANG", "chi_sim+eng")
    calls = install_fake_ocr(
        monkeypatch,
        languages=("chi_sim", "eng"),
    )

    result = extract_image(make_image_bytes(), "course.png")

    assert result["ok"] is True
    assert calls[0][1:] == ("chi_sim+eng", 15)


@pytest.mark.parametrize("filename", ["COURSE.PNG", "COURSE.JPG", "COURSE.JPEG"])
def test_extract_document_dispatches_images_case_insensitively(
    monkeypatch,
    filename,
):
    file_bytes = b"image bytes"
    result = {"ok": True, "selected": "image"}
    calls = []

    def fake_image(received_bytes, received_filename):
        calls.append((received_bytes, received_filename))
        return result

    monkeypatch.setattr(document_service, "extract_image", fake_image)

    extracted = document_service.extract_document(file_bytes, filename)

    assert extracted is result
    assert calls == [(file_bytes, filename)]


@pytest.mark.parametrize(
    ("file_bytes", "filename"),
    [
        (b"not an image", "corrupt.png"),
        (make_image_bytes("GIF"), "renamed.png"),
        (make_image_bytes("PNG"), "renamed.jpg"),
    ],
)
def test_extract_image_rejects_corrupt_or_mismatched_image_content(
    file_bytes,
    filename,
):
    result = extract_image(file_bytes, filename)

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_IMAGE"
    assert "not an image" not in result["message"]


def test_extract_image_rejects_empty_and_unsupported_inputs():
    empty_result = extract_image(b"", "empty.png")
    unsupported_result = extract_image(b"data", "photo.webp")

    assert empty_result["error_code"] == "EMPTY_DOCUMENT"
    assert unsupported_result["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_extract_image_checks_pixel_limit_before_full_decode(monkeypatch):
    class HeaderOnlyImage:
        format = "PNG"
        size = (5000, 4001)

        def __init__(self):
            self.loaded = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def load(self):
            self.loaded = True

        def convert(self, mode):
            pytest.fail("Pixel limit must be checked before conversion")

    image = HeaderOnlyImage()
    monkeypatch.setattr(document_service.Image, "open", lambda stream: image)
    monkeypatch.setattr(
        document_service,
        "_load_pytesseract",
        lambda: pytest.fail("OCR must not run for oversized images"),
        raising=False,
    )

    result = extract_image(b"header bytes", "oversized.png")

    assert result["ok"] is False
    assert result["error_code"] == "IMAGE_TOO_LARGE"
    assert image.loaded is False


def test_extract_image_enforces_file_size_limit(monkeypatch):
    file_bytes = make_image_bytes()
    monkeypatch.setattr(document_service, "MAX_FILE_BYTES", len(file_bytes))
    install_fake_ocr(monkeypatch)

    at_limit_result = extract_image(file_bytes, "at-limit.png")
    over_limit_result = extract_image(file_bytes + b"x", "over-limit.png")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "FILE_TOO_LARGE"


def test_extract_image_enforces_text_length_limit(monkeypatch):
    monkeypatch.setattr(document_service, "MAX_TEXT_CHARS", 4)
    install_fake_ocr(monkeypatch, text="1234")
    at_limit_result = extract_image(make_image_bytes(), "at-limit.png")
    install_fake_ocr(monkeypatch, text="12345")

    over_limit_result = extract_image(make_image_bytes(), "over-limit.png")

    assert at_limit_result["ok"] is True
    assert over_limit_result["ok"] is False
    assert over_limit_result["error_code"] == "TEXT_TOO_LONG"


def test_extract_image_returns_engine_unavailable_without_cloud_fallback(
    monkeypatch,
):
    def fail_if_gemini_called(**kwargs):
        pytest.fail("Local OCR failure must not call Gemini")

    monkeypatch.setattr(gemini_service.genai, "Client", fail_if_gemini_called)
    install_fake_ocr(
        monkeypatch,
        languages_error=FakeTesseractNotFoundError("/private/tesseract path"),
    )

    result = document_service.extract_document(
        make_image_bytes(),
        "course.png",
    )

    assert result["ok"] is False
    assert result["error_code"] == "OCR_ENGINE_UNAVAILABLE"
    assert "/private/tesseract path" not in result["message"]


def test_extract_image_returns_language_unavailable(monkeypatch):
    monkeypatch.setenv("OCR_LANG", "chi_sim")
    calls = install_fake_ocr(monkeypatch, languages=("eng",))

    result = extract_image(make_image_bytes(), "course.png")

    assert result["ok"] is False
    assert result["error_code"] == "OCR_LANGUAGE_UNAVAILABLE"
    assert calls == []


@pytest.mark.parametrize(
    ("ocr_error", "expected_error"),
    [
        (RuntimeError("Tesseract process timeout"), "OCR_TIMEOUT"),
        (FakeTesseractError("private OCR path and data"), "OCR_FAILED"),
    ],
)
def test_extract_image_returns_safe_timeout_and_execution_errors(
    monkeypatch,
    ocr_error,
    expected_error,
):
    install_fake_ocr(monkeypatch, ocr_error=ocr_error)

    result = extract_image(make_image_bytes(), "course.png")

    assert result["ok"] is False
    assert result["error_code"] == expected_error
    assert "private OCR path" not in result["message"]
    assert "private OCR path and data" not in result["message"]


def test_extract_image_rejects_empty_ocr_result(monkeypatch):
    install_fake_ocr(monkeypatch, text=" \n\t ")

    result = extract_image(make_image_bytes(), "blank.png")

    assert result["ok"] is False
    assert result["error_code"] == "NO_EXTRACTABLE_TEXT"


@pytest.mark.parametrize(
    ("filename", "selected_extractor"),
    [
        ("notes.txt", "txt"),
        ("NOTES.TXT", "txt"),
        ("course.pdf", "pdf"),
        ("COURSE.PDF", "pdf"),
    ],
)
@pytest.mark.parametrize("ok", [True, False])
def test_extract_document_dispatches_and_returns_result_unchanged(
    monkeypatch,
    filename,
    selected_extractor,
    ok,
):
    file_bytes = b"in-memory file bytes"
    result = {"ok": ok, "custom_field": object()}
    calls = []

    def fake_txt(received_bytes, received_filename):
        calls.append(("txt", received_bytes, received_filename))
        return result

    def fake_pdf(received_bytes, received_filename):
        calls.append(("pdf", received_bytes, received_filename))
        return result

    monkeypatch.setattr(document_service, "extract_txt", fake_txt)
    monkeypatch.setattr(document_service, "extract_pdf", fake_pdf)

    extracted = document_service.extract_document(file_bytes, filename)

    assert extracted is result
    assert calls == [(selected_extractor, file_bytes, filename)]


def test_extract_document_rejects_unsupported_type_without_calling_extractors(
    monkeypatch,
):
    def fail_if_called(*args):
        pytest.fail("An extractor must not be called for unsupported file types")

    monkeypatch.setattr(document_service, "extract_txt", fail_if_called)
    monkeypatch.setattr(document_service, "extract_pdf", fail_if_called)

    result = document_service.extract_document(b"data", "notes.docx")

    assert result == {
        "ok": False,
        "error_code": "UNSUPPORTED_FILE_TYPE",
        "message": "仅支持 TXT、文字型 PDF、文字型 PPTX 或 PNG/JPEG 图片。",
    }
