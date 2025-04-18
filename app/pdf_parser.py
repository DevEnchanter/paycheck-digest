
import io, os, json, base64, datetime as dt
import PyPDF2, fitz, openai
from dotenv import load_dotenv

load_dotenv()

TEXT_MODEL = os.getenv("MODEL_TEXT", "gpt-4o-mini")
VISION_MODEL = os.getenv("MODEL_VISION", "gpt-4o-mini")
MAX_COST_CENTS = int(os.getenv("MAX_COST_CENTS", "0"))
LEDGER_PATH = os.path.expanduser("~/.paydigest_budget.json")
RESPONSE_FORMAT = {"type": "json_object"}

def _budget_ok(cost=1):
    if MAX_COST_CENTS <= 0:
        return True
    rec = {"spent": 0, "month": dt.date.today().month}
    if os.path.exists(LEDGER_PATH):
        try: rec = json.load(open(LEDGER_PATH))
        except: pass
    if rec.get("month") != dt.date.today().month:
        rec = {"spent": 0, "month": dt.date.today().month}
    if rec["spent"] + cost > MAX_COST_CENTS:
        return False
    rec["spent"] += cost
    json.dump(rec, open(LEDGER_PATH, "w"))
    return True

def _selectable_text(pdf_bytes):
    try:
        rdr = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(p.extract_text() or "" for p in rdr.pages)
    except:
        return ""

def _first_page_png_b64(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300)
    png = pix.pil_tobytes(format="PNG")
    return base64.b64encode(png).decode()

def parse_paystub(pdf_bytes):
    if not _budget_ok(): return {"error": "Monthly LLM budget exhausted"}
    txt = _selectable_text(pdf_bytes)
    if txt.strip():
        messages = [
            {"role":"system","content":"""
You are a payroll data extractor. Redact all personal identifiers. Extract only current amounts. Return JSON with keys: period_start, period_end, gross_pay, net_pay, taxes, plain_english, html_summary. Only JSON.
"""}, {"role":"user","content":txt[:15000]}
        ]
        model = TEXT_MODEL
    else:
        b64 = _first_page_png_b64(pdf_bytes)
        messages = [
            {"role":"system","content":"""
You are a payroll data extractor. Redact all personal identifiers. Extract only current amounts from this image. Return JSON with keys: period_start, period_end, gross_pay, net_pay, taxes, plain_english, html_summary. Only JSON.
"""}, {"role":"user","content":[
    {"type":"image_url","image_url":{"url":"data:image/png;base64,"+b64}},
    {"type":"text","text":"Extract payroll data and include html_summary."}
]}]
        model = VISION_MODEL
    try:
        rsp = openai.chat.completions.create(model=model, messages=messages, response_format=RESPONSE_FORMAT)
        data = json.loads(rsp.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}
    if "html_summary" not in data and "plain_english" in data:
        data["html_summary"] = f"<div class='summary-card'><p>{data['plain_english']}</p></div>"
    return data
