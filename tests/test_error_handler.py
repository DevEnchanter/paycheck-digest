# tests/test_error_handler.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_global_error_handler():
    # We need a route that raises to test our handler; 
    # temporarily add this to your app or use an existing error
    response = client.get("/cause_error")
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Test exception" in data["detail"]
