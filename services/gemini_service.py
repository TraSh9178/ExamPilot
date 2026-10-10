import os

from google import genai
from google.genai.errors import APIError


def check_gemini_connection() -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "error_code": "MISSING_API_KEY",
            "message": "请配置 GEMINI_API_KEY",
        }

    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"

    try:
        with genai.Client(api_key=api_key) as client:
            response = client.models.generate_content(
                model=model,
                contents="Reply with only: ExamPilot API OK",
            )

        text = response.text
        if not text or not text.strip():
            return {
                "ok": False,
                "error_code": "EMPTY_RESPONSE",
                "message": "Gemini 返回了空响应。",
            }

        return {"ok": True, "model": model, "text": text}
    except APIError as exc:
        return {
            "ok": False,
            "error_code": "API_ERROR",
            "status_code": exc.code,
            "message": "Gemini API 请求失败，请检查配置或稍后重试。",
        }
    except Exception:
        return {
            "ok": False,
            "error_code": "CONNECTION_ERROR",
            "message": "连接 Gemini 时发生错误，请检查配置或网络后重试。",
        }