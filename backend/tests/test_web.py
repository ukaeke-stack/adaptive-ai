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


def test_voice_interface_guards_optional_speech_synthesis_api():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "speechSynthesis?.cancel()" not in response.text
    assert "'speechSynthesis' in window&&window.speechSynthesis.speaking" in response.text


def test_voice_interface_auto_sends_after_speech_ends_and_has_dynamic_robot():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "recognition.onspeechend" in response.text
    assert "Sending your spoken message automatically" in response.text
    assert "recognition.onend" in response.text
    assert "@keyframes roam" in response.text
    assert "@keyframes speakMove" in response.text
    assert "synth.resume()" in response.text
