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

# Load environment variables from .env
load_dotenv()

# Configuration
TEXT_MODEL = os.getenv("MODEL_TEXT", "gpt-4o-mini")
VISION_MODEL = os.getenv("MODEL_VISION", "gpt-4o-mini")
MAX_COST_CENTS = int(os.getenv("MAX_COST_CENTS", "0"))
LEDGER_PATH = os.path.expanduser("~/.paydigest_budget.json")

# Only 'type' is allowed in response_format
RESPONSE_FORMAT = {"type": "json_object"}


def _budget_ok(cost: int = 1) -> bool:
    """Return True if within monthly cost budget."""
    if MAX_COST_CENTS <= 0:
        return True
    record = {"spent": 0, "month": dt.date.today().month}
    if os.path.exists(LEDGER_PATH):
        try:
            record = json.load(open(LEDGER_PATH))
        except json.JSONDecodeError:
            pass
    if record.get("month") != dt.date.today().month:
        record = {"spent": 0, "month": dt.date.today().month}
    if record["spent"] + cost > MAX_COST_CENTS:
        return False
    record["spent"] += cost
    json.dump(record, open(LEDGER_PATH, "w"))
    return True


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
        return {"error": "Monthly LLM budget exhausted"}

    # 1) Try standard text extraction
    text = _selectable_text(pdf_bytes)
    ocr_fallback = False

    if text.strip():
        # Use the text branch
        messages = [
            {
                "role": "system",
                "content": """
You are a payroll data extractor. **Redact ALL personal identifiers** (employee name, address, SSN, employee ID, etc.).
Extract **only** the Current column amounts (ignore Year‑to‑Date). Return exactly this JSON:
  • period_start, period_end, gross_pay, net_pay, taxes, plain_english, html_summary
Respond ONLY with that JSON object.
""",
            },
            {"role": "user", "content": text[:15000]},
        ]
        model = TEXT_MODEL

    else:
        # Fallback to OCR branch
        ocr_fallback = True
        img_b64 = _first_page_png_b64(pdf_bytes)
        messages = [
            {
                "role": "system",
                "content": """
You are a payroll data extractor. **Redact ALL personal identifiers** (employee name, address, SSN, IDs).
This is from a scanned image—extract only the Current column amounts (ignore Y‑T‑D). Return exactly this JSON:
  • period_start, period_end, gross_pay, net_pay, taxes, plain_english, html_summary
Respond ONLY with that JSON object.
""",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + img_b64},
                    },
                    {
                        "type": "text",
                        "text": "Extract payroll data from this image, redact PII, include html_summary.",
                    },
                ],
            },
        ]
        model = VISION_MODEL

    try:
        resp = openai.chat.completions.create(
            model=model, messages=messages, response_format=RESPONSE_FORMAT
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"error": f"OpenAI call failed: {e}"}

    # Ensure html_summary exists
    if "html_summary" not in data and "plain_english" in data:
        data["html_summary"] = (
            f"<div class='summary-card'><p>{data['plain_english']}</p></div>"
        )

    # Inject our fallback flag
    data["ocr_fallback"] = ocr_fallback
    return data
