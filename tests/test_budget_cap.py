# tests/test_budget_cap.py

import io
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def exhaust_budget(monkeypatch):
    # Force _budget_ok to return False
    import app.pdf_parser as pp
    monkeypatch.setattr(pp, "_budget_ok", lambda cost=1: False)

def test_budget_cap_blocks_digest(tmp_path):
    # Create a dummy PDF file
    pdf_bytes = b"%PDF-1.4\n%%EOF"
    files = {"file": ("stub.pdf", pdf_bytes, "application/pdf")}

    resp = client.post("/digest", files=files)
    assert resp.status_code == 402
    data = resp.json()
    assert data["detail"] == "Monthly LLM budget exhausted" 