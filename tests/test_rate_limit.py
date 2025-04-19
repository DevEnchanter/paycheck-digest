# tests/test_rate_limit.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_digest_rate_limit(tmp_path):
    # Prepare a dummy PDF payload
    pdf_bytes = b"%PDF-1.4\n%%EOF"
    files = {"file": ("stub.pdf", pdf_bytes, "application/pdf")}
    
    # Send 5 successful requests
    for _ in range(5):
        resp = client.post("/digest", files=files)
        # We expect either 200 or 400 (depending on parsing),
        # but definitely not 429 yet.
        assert resp.status_code != 429

    # 6th request should be rate-limited
    resp = client.post("/digest", files=files)
    assert resp.status_code == 429
    assert resp.text == "Too many requests" 