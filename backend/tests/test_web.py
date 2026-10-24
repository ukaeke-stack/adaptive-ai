from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_voice_chat_interface_is_served_same_origin():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "Norah" in response.text
    assert "SpeechRecognition" in response.text
    assert "apiToken" not in response.text
    assert "Owner sign in" in response.text
    assert "Authorization':'Bearer" not in response.text
    assert "fetch('/v1/chat'" in response.text


def test_voice_interface_does_not_persist_api_token():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "sessionStorage" not in response.text
    assert "localStorage" not in response.text
    assert "credentials:'same-origin'" in response.text
    assert "localStorage" not in response.text


def test_voice_interface_guards_optional_speech_synthesis_api():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "speechSynthesis?.cancel()" not in response.text
    assert "'speechSynthesis' in window&&window.speechSynthesis.speaking" in response.text


def test_voice_input_auto_submits_when_recognition_ends():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "recognition.onend=()=>" in response.text
    assert "sendMessage(spoken)" in response.text
    assert "Review your message, then tap send." not in response.text


def test_robot_has_distinct_idle_listening_and_speaking_motion():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "@keyframes roam" in response.text
    assert "@keyframes listen-bob" in response.text
    assert "@keyframes speak-bob" in response.text


def test_account_forms_include_owner_enrollment_and_recovery():
    response = client.get("/app/")
    assert response.status_code == 200
    assert "/v1/auth/enroll-owner" in response.text
    assert "/v1/auth/login" in response.text
    assert "/v1/auth/recover" in response.text
    assert "ADAPTIVE_AI_API_TOKEN" not in response.text


def test_floating_robot_refreshes_authentication_before_listening_and_sending():
    response = client.get("/app/?overlay=1")
    assert response.status_code == 200
    page = response.text
    assert "await checkSession();" in page
    assert "async function activateFloatingRobot()" in page
    assert "The floating WebView can start before the main app's login completes." in page
    assert "await checkSession();\n if(!authenticated){const message='Please sign in to Adaptive AI in the main app, then tap Norah again.'" in page
