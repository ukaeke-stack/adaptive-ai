from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_vision_rejects_non_image_data_url():
    response = client.post("/v1/vision/analyze", json={"image_data_url": "https://example.com/photo.jpg"})
    assert response.status_code == 422


def test_vision_requires_provider_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    image = "data:image/jpeg;base64," + ("A" * 160)
    response = client.post("/v1/vision/analyze", json={"image_data_url": image, "prompt": "Read this"})
    # The payload is syntactically valid base64; the provider configuration is checked next.
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_vision_rejects_extra_fields():
    response = client.post("/v1/vision/analyze", json={
        "image_data_url": "data:image/jpeg;base64," + ("A" * 160),
        "admin": True,
    })
    assert response.status_code == 422
