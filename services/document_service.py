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
    "OCR_ENGINE_UNAVAILABLE": "本机 OCR 引擎不可用，请检查 Tesseract 安装。",
    "OCR_LANGUAGE_UNAVAILABLE": "本机 OCR 语言包不可用，请检查 OCR_LANG 配置。",
    "OCR_TIMEOUT": "图片文字识别超时，请尝试较小或更清晰的图片。",
    "OCR_FAILED": "图片文字识别失败，请检查图片后重试。",
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
            "message": "仅支持 .txt 文件。",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "文件大小不能超过 5 MiB。",
        }

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            "ok": False,
            "error_code": "INVALID_ENCODING",
            "message": "文件必须使用有效的 UTF-8 编码。",
        }

    if not text.strip():
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "文件内容为空。",
        }

    if len(text) > MAX_TEXT_CHARS:
        return {
            "ok": False,
            "error_code": "TEXT_TOO_LONG",
            "message": "文本长度不能超过 50,000 个字符。",
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
            "message": "仅支持 .pdf 文件。",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "PDF 文件内容为空。",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "文件大小不能超过 5 MiB。",
        }

    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
            if document.needs_pass:
                return {
                    "ok": False,
                    "error_code": "ENCRYPTED_PDF",
                    "message": "PDF 需要密码才能读取，暂不支持加密 PDF。",
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
                        "message": "PDF 提取文本长度超过 50,000 个字符。",
                    }

                if page_text.strip():
                    sources.append({"filename": filename, "page": page_number})

            if not sources:
                return {
                    "ok": False,
                    "error_code": "NO_EXTRACTABLE_TEXT",
                    "message": "PDF 中没有可提取的文字，可能是扫描件或空白 PDF；本功能不支持 OCR。",
                }

            text = "\n".join(page["text"] for page in pages)
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_PDF",
            "message": "无法读取 PDF，文件可能已损坏或内容不是有效的 PDF。",
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
            "message": "仅支持 .pptx 文件。",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "PPTX 文件内容为空。",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "文件大小不能超过 5 MiB。",
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
                    "message": "PPTX 提取文本长度超过 50,000 个字符。",
                }

            if slide_text.strip():
                sources.append({"filename": filename, "page": slide_number})

        if not sources:
            return {
                "ok": False,
                "error_code": "NO_EXTRACTABLE_TEXT",
                "message": "PPTX 中没有可提取的文字，可能是空白幻灯片或图片内容；本功能不支持 OCR。",
            }

        text = "\n".join(slide["text"] for slide in pages)
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_PPTX",
            "message": "无法读取 PPTX，文件可能已损坏或内容不是有效的 PPTX。",
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
            "message": "仅支持 .png、.jpg 或 .jpeg 图片。",
        }

    if not file_bytes:
        return {
            "ok": False,
            "error_code": "EMPTY_DOCUMENT",
            "message": "图片文件内容为空。",
        }

    if len(file_bytes) > MAX_FILE_BYTES:
        return {
            "ok": False,
            "error_code": "FILE_TOO_LARGE",
            "message": "文件大小不能超过 5 MiB。",
        }

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            if image.format != IMAGE_FORMATS[extension]:
                return {
                    "ok": False,
                    "error_code": "INVALID_IMAGE",
                    "message": "图片内容无效或格式与扩展名不符，仅支持 PNG/JPEG。",
                }

            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                return {
                    "ok": False,
                    "error_code": "IMAGE_TOO_LARGE",
                    "message": "图片像素数不能超过 20,000,000。",
                }

            image.load()
            ocr_image = image.convert("RGB")
    except Exception:
        return {
            "ok": False,
            "error_code": "INVALID_IMAGE",
            "message": "图片内容无效或格式与扩展名不符，仅支持 PNG/JPEG。",
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
            "message": "图片中没有可提取的文字。",
        }

    if len(text) > MAX_TEXT_CHARS:
        return {
            "ok": False,
            "error_code": "TEXT_TOO_LONG",
            "message": "图片提取文本长度超过 50,000 个字符。",
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
        "message": "仅支持 TXT、文字型 PDF、文字型 PPTX 或 PNG/JPEG 图片。",
    }
