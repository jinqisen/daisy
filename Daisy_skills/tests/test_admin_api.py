import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "tools_count" in data


def test_admin_metrics_unauthorized():
    response = client.get("/admin/metrics")
    assert response.status_code == 403


def test_admin_metrics_with_token():
    response = client.get("/admin/metrics?admin_token=admin_token_123")
    assert response.status_code == 200
    data = response.json()
    assert "timestamp" in data
    assert "tool_calls_total" in data
    assert "tool_latency_p95_ms" in data
    assert "error_rate" in data


def test_admin_workflow_traces_unauthorized():
    response = client.get("/admin/traces/workflow")
    assert response.status_code == 403


def test_admin_workflow_traces_with_token():
    response = client.get("/admin/traces/workflow?admin_token=admin_token_123")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    assert "execution_id" in data["items"][0]


def test_admin_llm_traces_unauthorized():
    response = client.get("/admin/traces/llm")
    assert response.status_code == 403


def test_admin_llm_traces_with_token():
    response = client.get("/admin/traces/llm?admin_token=admin_token_123")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    assert "timestamp" in data["items"][0]


def test_admin_reflexion_unauthorized():
    response = client.get("/admin/reflexion")
    assert response.status_code == 403


def test_admin_reflexion_with_token():
    response = client.get("/admin/reflexion?admin_token=admin_token_123")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    assert "timestamp" in data["items"][0]


def test_admin_metrics_invalid_token():
    response = client.get("/admin/metrics?admin_token=invalid_token")
    assert response.status_code == 401
