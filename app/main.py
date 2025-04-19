from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .database import init_db, SessionLocal, Paystub
from .pdf_parser import parse_paystub
import zipfile, io, json, numpy as np
from pydantic import BaseModel

# Initialize DB
init_db()

app = FastAPI(title="Paycheck Digest")

# Health check
@app.get("/health")
def health():
    return {"status": "ok"}

# Digest endpoint
@app.post("/digest")
async def digest(file: UploadFile = File(...)):
    name = file.filename.lower()
    data = await file.read()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            pdfs = [n for n in z.namelist() if n.lower().endswith(".pdf")]
            if not pdfs:
                raise HTTPException(400, "ZIP contains no PDF")
            data = z.read(pdfs[0])
    elif not name.endswith(".pdf"):
        raise HTTPException(400, "Only PDF or ZIP supported")

    result = parse_paystub(data)
    if "error" in result:
        raise HTTPException(500, result["error"])

    db = SessionLocal()
    try:
        stub = Paystub(
            period_start=result.get("period_start"),
            period_end=result.get("period_end"),
            gross_pay=result.get("gross_pay"),
            net_pay=result.get("net_pay"),
            taxes=result.get("taxes")
        )
        db.add(stub); db.commit(); db.refresh(stub)
    finally:
        db.close()

    return result

# History endpoint
@app.get("/history")
def history(limit: int = 20):
    db = SessionLocal()
    try:
        rows = (
            db.query(Paystub)
              .order_by(Paystub.created_at.desc())
              .limit(limit)
              .all()
        )
        return [
            {"period_start": r.period_start, "net_pay": r.net_pay}
            for r in rows
        ]
    finally:
        db.close()

# Analytics response model
class Analytics(BaseModel):
    total_gross:     float
    total_net:       float
    avg_net:         float
    min_net:         float
    max_net:         float
    tax_totals:      dict
    net_trend_slope: float
    anomalies:       list[dict]

# DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Analytics endpoint
@app.get("/analytics", response_model=Analytics)
def analytics(db: Session = Depends(get_db)):
    stubs = db.query(Paystub).all()
    if not stubs:
        return Analytics(
            total_gross=0.0,
            total_net=0.0,
            avg_net=0.0,
            min_net=0.0,
            max_net=0.0,
            tax_totals={},
            net_trend_slope=0.0,
            anomalies=[]
        )

    nets = np.array([s.net_pay for s in stubs], dtype=float)
    total_gross = float(sum(s.gross_pay for s in stubs))

    # Aggregate taxes safely
    tax_totals = {}
    for s in stubs:
        taxes = s.taxes
        if isinstance(taxes, str):
            try:
                taxes = json.loads(taxes)
            except:
                taxes = {}
        for k, v in (taxes or {}).items():
            try:
                tax_totals[k] = tax_totals.get(k, 0.0) + float(v)
            except:
                continue

    # Compute simple trend slope
    x = np.arange(len(nets))
    slope = float(np.polyfit(x, nets, 1)[0]) if len(nets) > 1 else 0.0

    # Detect >10% anomalies against 3‑period moving avg
    anomalies = []
    for i in range(3, len(nets)):
        window = nets[i-3:i]
        if window.mean() and abs(nets[i] - window.mean()) / window.mean() > 0.10:
            anomalies.append({
                "period_start": stubs[i].period_start,
                "net_pay":      float(nets[i])
            })

    return Analytics(
        total_gross=total_gross,
        total_net=float(nets.sum()),
        avg_net=float(nets.mean()),
        min_net=float(nets.min()),
        max_net=float(nets.max()),
        tax_totals=tax_totals,
        net_trend_slope=slope,
        anomalies=anomalies
    )

# Mount the React build directory last,
# so all /health, /digest, /history, /analytics routes match first.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
