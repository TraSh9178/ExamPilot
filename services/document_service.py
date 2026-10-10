MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 50_000


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