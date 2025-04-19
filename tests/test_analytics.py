# tests/test_analytics.py

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app, init_db, SessionLocal, Paystub

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_db(tmp_path, monkeypatch):
    """
    Override the SQLite DB to use a temp file for each test run,
    then recreate the tables.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    yield
    # cleanup happens automatically

def insert_stub(session, period_start, net_pay, gross_pay=0.0, taxes=None):
    stub = Paystub(
        period_start=period_start,
        period_end=period_start,
        gross_pay=gross_pay,
        net_pay=net_pay,
        taxes=taxes or {}
    )
    session.add(stub)
    session.commit()

def test_analytics_empty():
    """When no records exist, analytics should return all zeros."""
    resp = client.get("/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "total_gross": 0.0,
        "total_net": 0.0,
        "avg_net": 0.0,
        "min_net": 0.0,
        "max_net": 0.0,
        "tax_totals": {},
        "net_trend_slope": 0.0,
        "anomalies": []
    }

def test_analytics_with_data():
    """With some stubs inserted, analytics should compute correct aggregates."""
    db = SessionLocal()
    # insert three stubs
    insert_stub(db, "2025-04-01", net_pay=100.0, gross_pay=150.0, taxes={"Fed": 10})
    insert_stub(db, "2025-04-08", net_pay=200.0, gross_pay=250.0, taxes={"Fed": 20})
    insert_stub(db, "2025-04-15", net_pay=300.0, gross_pay=350.0, taxes={"Fed": 30})
    db.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200

    data = resp.json()
    # total gross = 150+250+350 = 750
    assert data["total_gross"] == pytest.approx(750.0)
    # total net = 100+200+300 = 600
    assert data["total_net"] == pytest.approx(600.0)
    # avg net = 600/3 = 200
    assert data["avg_net"] == pytest.approx(200.0)
    # min net = 100, max net = 300
    assert data["min_net"] == pytest.approx(100.0)
    assert data["max_net"] == pytest.approx(300.0)
    # tax totals
    assert data["tax_totals"] == {"Fed": pytest.approx(60.0)}
    # slope should be positive
    assert data["net_trend_slope"] > 0
    # with only 3 points, no anomalies (need 4th to trigger)
    assert data["anomalies"] == []
