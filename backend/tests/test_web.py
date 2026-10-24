from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_voice_chat_interface_is_served_same_origin():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "Adaptive AI" in response.text
    assert "SpeechRecognition" in response.text
    assert "ADAPTIVE_AI_API_TOKEN" in response.text
    assert "fetch('/v1/chat'" in response.text


def test_voice_interface_does_not_persist_api_token():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "sessionStorage" not in response.text
    assert "localStorage" not in response.text
