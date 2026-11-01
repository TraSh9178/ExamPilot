import importlib
import os
import re
from io import BytesIO

import pymupdf
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
MAX_IMAGE_PIXELS = 20_000_000
OCR_TIMEOUT_SECONDS = 15

IMAGE_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}
OCR_ERROR_MESSAGES = {
    "OCR_ENGINE_UNAVAILABLE": "The OCR engine is not available on this server. Check the Tesseract installation.",
    "OCR_LANGUAGE_UNAVAILABLE": "The OCR language data is not available on this server. Check the OCR_LANG setting.",
    "OCR_TIMEOUT": "Text recognition timed out. Try a smaller or clearer image.",
    "OCR_FAILED": "Text recognition failed. Check the image and try again.",
}


class _OCRFailure(Exception):
    def __init__(self, error_code):
        self.error_code = error_code


def _load_pytesseract():
    return importlib.import_module("pytesseract")


def _run_ocr(image):
    configured_languages = os.getenv("OCR_LANG", "eng").strip() or "eng"
    language_codes = configured_languages.split("+")
    if any(not re.fullmatch(r"[a-z_]+", code) for code in language_codes):
        raise _OCRFailure("OCR_LANGUAGE_UNAVAILABLE")

    try:
        pytesseract = _load_pytesseract()
    except ModuleNotFoundError:
        raise _OCRFailure("OCR_ENGINE_UNAVAILABLE") from None

    try:
        installed_languages = set(pytesseract.get_languages(config=""))
    except pytesseract.TesseractNotFoundError:
        raise _OCRFailure("OCR_ENGINE_UNAVAILABLE") from None
    except Exception:
        raise _OCRFailure("OCR_FAILED") from None

    if not set(language_codes).issubset(installed_languages):
        raise _OCRFailure("OCR_LANGUAGE_UNAVAILABLE")

    try:
        return pytesseract.image_to_string(
            image,
            lang=configured_languages,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except pytesseract.TesseractNotFoundError:
        raise _OCRFailure("OCR_ENGINE_UNAVAILABLE") from None
    except pytesseract.TesseractError as error:
        error_text = str(getattr(error, "message", "")).casefold()
        if "failed loading language" in error_text or "error opening data file" in error_text:
            raise _OCRFailure("OCR_LANGUAGE_UNAVAILABLE") from None
        raise _OCRFailure("OCR_FAILED") from None
    except RuntimeError as error:
        if str(error) == "Tesseract process timeout":
            raise _OCRFailure("OCR_TIMEOUT") from None
        raise _OCRFailure("OCR_FAILED") from None
    except Exception:
        raise _OCRFailure("OCR_FAILED") from None


def _shape_texts(shapes):
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _shape_texts(shape.shapes)
        elif shape.has_table:
            for row in shape.table.rows:
                yield "\t".join(cell.text for cell in row.cells)
        elif shape.has_text_frame:
            yield shape.text_frame.text


def extract_txt(file_bytes: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".txt"):
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .txt files are supported.",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "The file must be 5 MiB or smaller.",
        }

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            "ok": False,
            "error_code": "INVALID_ENCODING",
            "message": "The file must be valid UTF-8 text.",
        }

    if not text.strip():
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "The file is empty.",
        }

    if len(text) > MAX_TEXT_CHARS:
        return {
            "ok": False,
            "error_code": "TEXT_TOO_LONG",
            "message": "The text must be 50,000 characters or fewer.",
        }

    return {
        "ok": True,
        "filename": filename,
        "text": text,
        "sources": [{"filename": filename, "page": None}],
    }


def extract_pdf(file_bytes: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".pdf"):
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .pdf files are supported.",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "The PDF file is empty.",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "The file must be 5 MiB or smaller.",
        }

    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
            if document.needs_pass:
                return {
                    "ok": False,
                    "error_code": "ENCRYPTED_PDF",
                    "message": "The PDF is password-protected. Encrypted PDFs are not supported.",
                }

            pages = []
            sources = []
            total_text_chars = 0

            for page_number, page in enumerate(document, start=1):
                page_text = page.get_text()
                pages.append({"page": page_number, "text": page_text})

                if page_number > 1:
                    total_text_chars += 1
                total_text_chars += len(page_text)
                if total_text_chars > MAX_TEXT_CHARS:
                    return {
                        "ok": False,
                        "error_code": "TEXT_TOO_LONG",
                        "message": "The text extracted from the PDF exceeds 50,000 characters.",
                    }

                if page_text.strip():
                    sources.append({"filename": filename, "page": page_number})

            if not sources:
                return {
                    "ok": False,
                    "error_code": "NO_EXTRACTABLE_TEXT",
                    "message": "No extractable text was found in the PDF. It may be scanned or blank; OCR is not supported for PDFs.",
                }

            text = "\n".join(page["text"] for page in pages)
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_PDF",
            "message": "The PDF could not be read. The file may be damaged or not a valid PDF.",
        }

    return {
        "ok": True,
        "filename": filename,
        "text": text,
        "pages": pages,
        "sources": sources,
    }


def extract_pptx(file_bytes: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".pptx"):
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .pptx files are supported.",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "The PPTX file is empty.",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "The file must be 5 MiB or smaller.",
        }

    try:
        presentation = Presentation(BytesIO(file_bytes))
        pages = []
        sources = []
        total_text_chars = 0

        for slide_number, slide in enumerate(presentation.slides, start=1):
            slide_text = "\n".join(
                text for text in _shape_texts(slide.shapes) if text
            )
            pages.append({"page": slide_number, "text": slide_text})

            if slide_number > 1:
                total_text_chars += 1
            total_text_chars += len(slide_text)
            if total_text_chars > MAX_TEXT_CHARS:
                return {
                    "ok": False,
                    "error_code": "TEXT_TOO_LONG",
                    "message": "The text extracted from the PPTX exceeds 50,000 characters.",
                }

            if slide_text.strip():
                sources.append({"filename": filename, "page": slide_number})

        if not sources:
            return {
                "ok": False,
                "error_code": "NO_EXTRACTABLE_TEXT",
                "message": "No extractable text was found in the PPTX. The slides may be blank or image-only; OCR is not supported for PPTX.",
            }

        text = "\n".join(slide["text"] for slide in pages)
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_PPTX",
            "message": "The PPTX could not be read. The file may be damaged or not a valid PPTX.",
        }

    return {
        "ok": True,
        "filename": filename,
        "text": text,
        "pages": pages,
        "sources": sources,
    }


def extract_image(file_bytes: bytes, filename: str) -> dict:
    extension = next(
        (suffix for suffix in IMAGE_FORMATS if filename.lower().endswith(suffix)),
        None,
    )
    if extension is None:
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .png, .jpg, or .jpeg images are supported.",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "The image file is empty.",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "The file must be 5 MiB or smaller.",
        }

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            if image.format != IMAGE_FORMATS[extension]:
                return {
                    "ok": False,
                    "error_code": "INVALID_IMAGE",
                    "message": "The image is invalid or its format does not match the file extension. Only PNG and JPEG are supported.",
                }

            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                return {
                    "ok": False,
                    "error_code": "IMAGE_TOO_LARGE",
                    "message": "The image must have 20,000,000 pixels or fewer.",
                }

            image.load()
            ocr_image = image.convert("RGB")
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_IMAGE",
            "message": "The image is invalid or its format does not match the file extension. Only PNG and JPEG are supported.",
        }

    try:
        try:
            text = _run_ocr(ocr_image)
        except _OCRFailure as error:
            return {
                "ok": False,
                "error_code": error.error_code,
                "message": OCR_ERROR_MESSAGES[error.error_code],
            }
        except Exception:
            return {
                "ok": False,
                "error_code": "OCR_FAILED",
                "message": OCR_ERROR_MESSAGES["OCR_FAILED"],
            }
    finally:
        ocr_image.close()

    if not isinstance(text, str):
        return {
            "ok": False,
            "error_code": "OCR_FAILED",
            "message": OCR_ERROR_MESSAGES["OCR_FAILED"],
        }

    if not text.strip():
        return {
            "ok": False,
            "error_code": "NO_EXTRACTABLE_TEXT",
            "message": "No text was recognised in the image.",
        }

    if len(text) > MAX_TEXT_CHARS:
        return {
            "ok": False,
            "error_code": "TEXT_TOO_LONG",
            "message": "The text recognised in the image exceeds 50,000 characters.",
        }

    return {
        "ok": True,
        "filename": filename,
        "text": text,
        "pages": [{"page": 1, "text": text}],
        "sources": [{"filename": filename, "page": 1}],
    }


def extract_document(file_bytes: bytes, filename: str) -> dict:
    if filename.lower().endswith(".txt"):
        return extract_txt(file_bytes, filename)

    if filename.lower().endswith(".pdf"):
        return extract_pdf(file_bytes, filename)

    if filename.lower().endswith(".pptx"):
        return extract_pptx(file_bytes, filename)

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):
        return extract_image(file_bytes, filename)

    return {
        "ok": False,
        "error_code": "UNSUPPORTED_FILE_TYPE",
        "message": "Only TXT, text-based PDF, text-based PPTX, or PNG/JPEG images are supported.",
    }
