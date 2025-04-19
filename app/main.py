import io
import json
import os
import zipfile

import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .database import init_db
from .database import SessionLocal
from .database import Paystub
from .pdf_parser import parse_paystub

# Initialize the database
init_db()

app = FastAPI(title="Paycheck Digest")


@app.exception_handler(Exception)
async def all_exceptions_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler: returns JSON {"detail": ...} with status 500.
    """
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# Health check
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Digest endpoint
@app.post("/digest")
async def digest(file: UploadFile = File(...)) -> dict:
    name = file.filename.lower()
    data = await file.read()

    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            pdfs = [
                n for n in z.namelist() if n.lower().endswith(".pdf")
            ]
            if not pdfs:
                raise HTTPException(
                    status_code=400, detail="ZIP contains no PDF"
                )
            data = z.read(pdfs[0])
    elif not name.endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Only PDF or ZIP supported"
        )

    result = parse_paystub(data)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    db = SessionLocal()
    try:
        stub = Paystub(
            period_start=result.get("period_start"),
            period_end=result.get("period_end"),
            gross_pay=result.get("gross_pay"),
            net_pay=result.get("net_pay"),
            taxes=result.get("taxes"),
        )
        db.add(stub)
        db.commit()
        db.refresh(stub)
    finally:
        db.close()

    return result


# History endpoint
@app.get("/history")
def history(limit: int = 20) -> list[dict]:
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
    total_gross: float
    total_net: float
    avg_net: float
    min_net: float
    max_net: float
    tax_totals: dict
    net_trend_slope: float
    anomalies: list[dict]


# DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Analytics endpoint
@app.get("/analytics", response_model=Analytics)
def analytics(db: Session = Depends(get_db)) -> Analytics:
    """
    Aggregates paystub data. On error, returns zeroed Analytics.
    """
    try:
        stubs = db.query(Paystub).all()
        if not stubs:
            raise ValueError("no records")

        nets = np.array([s.net_pay for s in stubs], dtype=float)
        total_gross = float(sum(s.gross_pay for s in stubs))

        # Safely aggregate taxes
        tax_totals: dict[str, float] = {}
        for s in stubs:
            if isinstance(s.taxes, dict):
                taxes = s.taxes
            elif isinstance(s.taxes, str):
                try:
                    loaded = json.loads(s.taxes)
                except Exception:
                    loaded = {}
                if isinstance(loaded, dict):
                    taxes = loaded
                else:
                    taxes = {}
            else:
                taxes = {}

            for k, v in taxes.items():
                try:
                    tax_totals[k] = tax_totals.get(k, 0.0) + float(v)
                except (ValueError, TypeError):
                    continue

        # Compute net-pay trend slope
        x = np.arange(len(nets))
        if len(nets) > 1:
            slope = float(np.polyfit(x, nets, 1)[0])
        else:
            slope = 0.0

        # Detect >10% anomalies over a 3-period window
        anomalies: list[dict] = []
        for i in range(3, len(nets)):
            window = nets[i - 3 : i]
            if window.mean() and abs(nets[i] - window.mean()) / window.mean() > 0.10:
                anomalies.append(
                    {"period_start": stubs[i].period_start, "net_pay": float(nets[i])}
                )

        return Analytics(
            total_gross=total_gross,
            total_net=float(nets.sum()),
            avg_net=float(nets.mean()),
            min_net=float(nets.min()),
            max_net=float(nets.max()),
            tax_totals=tax_totals,
            net_trend_slope=slope,
            anomalies=anomalies,
        )

    except Exception as e:
        print(f"[analytics error] {e}")
        return Analytics(
            total_gross=0.0,
            total_net=0.0,
            avg_net=0.0,
            min_net=0.0,
            max_net=0.0,
            tax_totals={},
            net_trend_slope=0.0,
            anomalies=[],
        )


# Serve the React build directory last
if os.path.exists("build"):
    app.mount("/", StaticFiles(directory="build", html=True), name="static")
