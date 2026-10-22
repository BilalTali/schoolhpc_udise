"""
PARAKH Arithmetic Captcha Auto-Solver
Fetches the live arithmetic captcha from PARAKH, extracts the math expression
via OCR (pytesseract) or image analysis, and returns the solved answer.
"""
from typing import Dict, Any, Optional
import base64
import io
import re
import requests

PARAKH_BASE = "https://hpc.parakh.ncert.gov.in"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{PARAKH_BASE}/login/SCHOOL,TEACHER",
    "Content-Type": "application/json"
}


def _ocr_solve_from_base64(image_b64: str) -> Optional[str]:
    """
    Attempts to OCR-extract and solve an arithmetic expression from a base64 image.
    Returns the numeric answer as a string, or None if it fails.
    """
    try:
        import pytesseract
        from PIL import Image

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("L")  # grayscale

        # Threshold to make text cleaner
        img = img.point(lambda p: 0 if p < 128 else 255)

        # Run OCR
        text = pytesseract.image_to_string(
            img,
            config="--psm 7 -c tessedit_char_whitelist=0123456789+-*/x= ?"
        ).strip()

        return _evaluate_math_expression(text)
    except Exception:
        return None


def _evaluate_math_expression(text: str) -> Optional[str]:
    """
    Parses and evaluates simple arithmetic from OCR text.
    Supports: addition (+), subtraction (-), multiplication (* or x), division (/).
    """
    # Normalize: remove spaces, '=' and '?'
    expr = text.replace(" ", "").replace("=", "").replace("?", "").lower()

    # Try different arithmetic patterns
    # Addition: e.g. 3+5, 12+7
    m = re.search(r"(\d+)\+(\d+)", expr)
    if m:
        return str(int(m.group(1)) + int(m.group(2)))

    # Subtraction: e.g. 15-7
    m = re.search(r"(\d+)-(\d+)", expr)
    if m:
        result = int(m.group(1)) - int(m.group(2))
        return str(result)

    # Multiplication: e.g. 3*5 or 3x5
    m = re.search(r"(\d+)[*x](\d+)", expr)
    if m:
        return str(int(m.group(1)) * int(m.group(2)))

    # Division: e.g. 10/2
    m = re.search(r"(\d+)/(\d+)", expr)
    if m:
        divisor = int(m.group(2))
        if divisor != 0:
            return str(int(m.group(1)) // divisor)

    return None


def fetch_and_solve_captcha() -> Dict[str, Any]:
    """
    Fetches a live PARAKH captcha, auto-solves the arithmetic, and returns:
    {
        "success": True,
        "captcha_id": "...",
        "answer": "8",          # solved answer
        "image_base64": "..."   # for display if needed
    }
    """
    try:
        # 1. Fetch captcha from PARAKH
        url = f"{PARAKH_BASE}/api/proxy/captcha"
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)

        if resp.status_code != 200:
            return {"success": False, "error": f"PARAKH captcha service returned {resp.status_code}"}

        data = resp.json()
        if not (data.get("success") and data.get("data")):
            return {"success": False, "error": "Invalid captcha response from PARAKH"}

        captcha_data = data["data"]
        captcha_id = captcha_data.get("captcha_id", "")
        image_b64 = captcha_data.get("image_base64", "")

        # 2. Try to solve using OCR
        answer = _ocr_solve_from_base64(image_b64) if image_b64 else None

        # 3. If OCR fails, try text-based question from response (some captcha APIs return question text)
        if not answer:
            question_text = captcha_data.get("question") or captcha_data.get("text") or ""
            if question_text:
                answer = _evaluate_math_expression(question_text)

        if answer is not None:
            return {
                "success": True,
                "captcha_id": captcha_id,
                "answer": answer,
                "image_base64": image_b64
            }
        else:
            # Return captcha data for manual solving as fallback
            return {
                "success": True,
                "captcha_id": captcha_id,
                "answer": None,
                "image_base64": image_b64,
                "needs_manual": True,
                "message": "Auto-solve unavailable; please enter answer manually."
            }

    except Exception as e:
        return {"success": False, "error": f"Captcha fetch/solve error: {str(e)}"}


def verify_captcha_answer(captcha_id: str, answer: str) -> Dict[str, Any]:
    """Verifies a captcha answer with PARAKH and returns the captcha_token."""
    try:
        verify_url = f"{PARAKH_BASE}/api/proxy/captcha/verify"
        resp = requests.post(
            verify_url,
            json={"captcha_id": captcha_id, "answer": str(answer).strip()},
            headers=DEFAULT_HEADERS,
            timeout=10
        )
        if resp.status_code == 200:
            cap_data = resp.json()
            captcha_token = cap_data.get("data", {}).get("captcha_token") or ""
            return {"success": True, "captcha_token": captcha_token}
        return {"success": False, "error": f"Captcha verification failed (HTTP {resp.status_code})"}
    except Exception as e:
        return {"success": False, "error": str(e)}
