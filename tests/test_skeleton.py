"""Phase 1 skeleton verification tests."""

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import app


def test_settings_load_with_runtime_environment():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "gemini"
    assert settings.gemini_model == ""
    assert settings.backend_port == 8000


def test_health_route():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "curapharm"}

