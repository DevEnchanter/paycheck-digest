"""
app/pdf_parser.py – LLM parser with PII redaction, HTML summary, and OCR fallback
"""

import base64
import datetime as dt
import io
import json
import os

import fitz
import openai
import PyPDF2
from dotenv import load_dotenv
from app.llm_client import LlmClient, UsageQuotaExceeded
from app.config import settings

# Load environment variables from .env
load_dotenv()

# Configuration
TEXT_MODEL = os.getenv("MODEL_TEXT", "gpt-4o-mini")
VISION_MODEL = os.getenv("MODEL_VISION", "gpt-4o-mini")
MAX_COST_CENTS = int(os.getenv("MAX_COST_CENTS", "0"))
LEDGER_PATH = os.path.expanduser("~/.paydigest_budget.json")

# Only 'type' is allowed in response_format
RESPONSE_FORMAT = {"type": "json_object"}

# TODO(Issue #6): Replace this with a robust budget check.
_budget = 10000  # Placeholder budget
_spent = 0  # Placeholder spending


def _budget_ok(cost=1) -> bool:
    """Return True if the cost is within budget, False otherwise."""
    global _spent
    if _spent + cost <= _budget:
        _spent += cost
        return True
    return False


def _selectable_text(pdf_bytes: bytes) -> str:
    """Extract selectable text from PDF pages."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _first_page_png_b64(pdf_bytes: bytes) -> str:
    """Rasterize first PDF page to PNG and return base64 string."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300)
    png_bytes = pix.pil_tobytes(format="PNG")
    return base64.b64encode(png_bytes).decode()


def parse_paystub(pdf_bytes: bytes) -> dict:
    """
    Parse the paystub PDF (bytes) and return a dict:
      - period_start  (MM/DD/YYYY)
      - period_end    (MM/DD/YYYY)
      - gross_pay     (number)
      - net_pay       (number)
      - taxes         (dict of tax_name: number)
      - ocr_fallback  (bool)  <-- new fallback flag
      - plain_english (string summary, no PII)
      - html_summary  (HTML snippet)
    All personal identifiers (names, addresses, SSNs, IDs) are redacted.
    """
    if not _budget_ok():
        # Budget exhausted → HTTP 402
        from fastapi import HTTPException

        raise HTTPException(
            status_code=402,
            detail="Monthly LLM budget exhausted"
        )

    try:
        llm_client = LlmClient(api_key=settings.openai_api_key)
        digest = llm_client.digest_paystub(pdf_bytes=pdf_bytes)
    except UsageQuotaExceeded:
        # TODO(Issue #7): Propagate this error to the user.
        return {"error": "OpenAI quota exceeded"}

    return digest
