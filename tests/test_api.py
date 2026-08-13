import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data
    assert "podman" in data["checks"]
    assert "models_directory" in data["checks"]

def test_api_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "exists" in data
    assert "running" in data
    assert "image_downloaded" in data

def test_api_config_endpoint():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "server" in data
    assert "gpu" in data
    assert "podman" in data
    assert "model" in data
    # Security check: API key itself should not be leaked in config dict
    assert "api_key" not in data.get("security", {})
    assert "api_key_set" in data.get("security", {})

def test_v1_models_endpoint():
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)

def test_ollama_tags_endpoint():
    response = client.get("/api/tags")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert isinstance(data["models"], list)

def test_ollama_ps_endpoint():
    response = client.get("/api/ps")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data

def test_ollama_version_endpoint():
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data

def test_api_start_validation_failure():
    # Test invalid model name with path traversal
    response = client.post("/api/start", json={"model_name": "../../etc/passwd"})
    assert response.status_code == 400
    assert "Invalid input" in response.json()["detail"]

def test_api_start_invalid_max_model_len():
    response = client.post("/api/start", json={"model_name": "ValidModel", "max_model_len": 50})
    assert response.status_code == 400
    assert "max_model_len must be between 128 and 8192" in response.json()["detail"]
