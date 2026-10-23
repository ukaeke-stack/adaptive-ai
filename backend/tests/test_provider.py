import json
import httpx
import pytest
import app.ai.provider as provider


def test_groq_defaults_and_request_are_correct(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-secret")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "  Hello from Groq  "}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider.httpx, "Client", lambda **kwargs: client)
    assert provider.generate_reply("Hello") == "Hello from Groq"
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-groq-secret"
    assert captured["payload"]["model"] == "openai/gpt-oss-20b"
    assert captured["payload"]["messages"][-1] == {"role": "user", "content": "Hello"}
    assert "test-groq-secret" not in json.dumps(captured["payload"])
    client.close()


def test_missing_groq_key_fails_without_network(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(provider.ProviderNotConfigured, match="key is not configured"):
        provider.generate_reply("Hello")


@pytest.mark.parametrize("base_url", ["http://api.groq.com/openai/v1", "https://example.com/v1", "https://user:pass@api.groq.com/openai/v1"])
def test_untrusted_base_url_is_rejected(monkeypatch, base_url):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-secret")
    monkeypatch.setenv("GROQ_BASE_URL", base_url)
    with pytest.raises(provider.ProviderNotConfigured, match="official HTTPS API host"):
        provider.generate_reply("Hello")


def test_provider_error_does_not_leak_raw_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-secret")

    def handler(request):
        return httpx.Response(401, text="secret account diagnostic")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider.httpx, "Client", lambda **kwargs: client)
    with pytest.raises(provider.ProviderRequestError) as exc:
        provider.generate_reply("Hello")
    assert "secret account diagnostic" not in str(exc.value)
    assert "test-groq-secret" not in str(exc.value)
    client.close()
