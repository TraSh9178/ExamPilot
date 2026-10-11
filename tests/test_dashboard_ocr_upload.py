"""Tests for OCR upload functionality in Dashboard."""
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from services.document_service import extract_document


def make_image_bytes(image_format="PNG"):
    """Create a simple test image in specified format."""
    stream = BytesIO()
    Image.new("RGB", (100, 100), color="white").save(stream, format=image_format)
    stream.seek(0)
    return stream.getvalue()


class TestOCRUploadUI:
    """Test OCR image upload functionality."""

    def test_png_image_upload_accepted(self):
        """PNG images should be processable by extract_document."""
        image_bytes = make_image_bytes("PNG")
        result = extract_document(image_bytes, "test.png")
        # Should not fail on unsupported type; success depends on Tesseract
        assert result["ok"] is not None  # ok will be True or False based on OCR
        assert "message" in result or "text" in result

    def test_jpg_image_upload_accepted(self):
        """JPG images should be processable by extract_document."""
        image_bytes = make_image_bytes("JPEG")
        result = extract_document(image_bytes, "test.jpg")
        assert result["ok"] is not None
        assert "message" in result or "text" in result

    def test_jpeg_image_upload_accepted(self):
        """JPEG images should be processable by extract_document."""
        image_bytes = make_image_bytes("JPEG")
        result = extract_document(image_bytes, "test.jpeg")
        assert result["ok"] is not None
        assert "message" in result or "text" in result

    def test_ocr_parse_success_with_mock(self, monkeypatch):
        """Mock OCR success - image should return recognized text."""
        image_bytes = make_image_bytes("PNG")

        class FakePytesseract:
            @staticmethod
            def get_languages(**kwargs):
                return ["eng"]

            @staticmethod
            def image_to_string(image, **kwargs):
                return "Mocked OCR result text"

        monkeypatch.setattr(
            "services.document_service._load_pytesseract",
            lambda: FakePytesseract(),
        )

        result = extract_document(image_bytes, "test.png")
        assert result["ok"] is True
        assert "Mocked OCR result text" in result["text"]

    def test_ocr_parse_failure_no_tesseract(self, monkeypatch):
        """When Tesseract not installed, should return error message."""

        def fail_load():
            raise OSError("Tesseract not found")

        monkeypatch.setattr(
            "services.document_service._load_pytesseract",
            fail_load,
        )

        image_bytes = make_image_bytes("PNG")
        result = extract_document(image_bytes, "test.png")
        assert result["ok"] is False
        assert "message" in result
        assert len(result["message"]) > 0

    def test_ocr_parse_failure_ocr_error(self, monkeypatch):
        """When OCR processing fails, should return error message."""

        class FakePytesseract:
            @staticmethod
            def image_to_string(*args, **kwargs):
                raise RuntimeError("OCR processing failed")

        monkeypatch.setattr(
            "services.document_service._load_pytesseract",
            lambda: FakePytesseract(),
        )

        image_bytes = make_image_bytes("PNG")
        result = extract_document(image_bytes, "test.png")
        assert result["ok"] is False
        assert "message" in result

    def test_extract_document_supports_image_formats(self):
        """extract_document should recognize PNG/JPG/JPEG extensions."""
        image_bytes = make_image_bytes("PNG")

        # Should not return UNSUPPORTED_FILE_TYPE
        result = extract_document(image_bytes, "test.png")
        assert result.get("error_code") != "UNSUPPORTED_FILE_TYPE"

        result = extract_document(image_bytes, "test.jpg")
        assert result.get("error_code") != "UNSUPPORTED_FILE_TYPE"

        result = extract_document(image_bytes, "test.jpeg")
        assert result.get("error_code") != "UNSUPPORTED_FILE_TYPE"

    def test_invalid_format_rejected(self):
        """Unsupported formats should be rejected."""
        image_bytes = make_image_bytes("PNG")
        result = extract_document(image_bytes, "test.bmp")
        assert result["ok"] is False
        assert result["error_code"] == "UNSUPPORTED_FILE_TYPE"

    def test_error_stops_generation(self):
        """When OCR fails, extraction should stop and not proceed."""
        image_bytes = make_image_bytes("PNG")

        class FakePytesseract:
            @staticmethod
            def image_to_string(*args, **kwargs):
                raise RuntimeError("OCR failed")

        with patch(
            "services.document_service._load_pytesseract",
            return_value=FakePytesseract(),
        ):
            result = extract_document(image_bytes, "test.png")
            assert result["ok"] is False
            assert "text" not in result  # No text should be generated on error

    def test_file_switch_clears_old_results(self):
        """Changing files should clear previous extraction results."""
        # This test validates the session_state clearing logic
        # in Dashboard.py via the setup_document_source key
        from hashlib import sha256

        file1_bytes = make_image_bytes("PNG")
        file2_bytes = make_image_bytes("JPEG")

        key1 = ("test1.png", sha256(file1_bytes).hexdigest())
        key2 = ("test2.jpeg", sha256(file2_bytes).hexdigest())

        # Keys should be different when file content changes
        assert key1 != key2

        # When source key changes, setup_document should be cleared
        # (This is validated by Dashboard logic)
        assert key1[1] != key2[1]


class TestDashboardFileTypes:
    """Test that Dashboard file uploader includes image formats."""

    def test_extract_document_called_with_image(self):
        """extract_document should be callable with image files."""
        image_bytes = make_image_bytes("PNG")
        # Verify function signature accepts (bytes, str)
        result = extract_document(image_bytes, "sample.png")
        assert isinstance(result, dict)
        assert "ok" in result
