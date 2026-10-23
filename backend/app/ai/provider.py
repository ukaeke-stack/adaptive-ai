"""OpenAI-compatible chat-completions adapter.

Provider credentials are read from environment variables and are never returned to clients.
"""
import os
import httpx


class ProviderNotConfigured(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


def generate_reply(message: str) -> str:
    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.getenv("AI_MODEL", "").strip()
    if not api_key or not model:
        raise ProviderNotConfigured("AI provider is not configured")
    if not base_url.startswith("https://"):
        raise ProviderNotConfigured("AI_BASE_URL must use HTTPS")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are Adaptive AI, a helpful assistant. Be clear and honest about uncertainty. Do not claim to have performed actions you have not performed. You cannot execute code, access private accounts, or control devices in this version."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.4,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        answer = data["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderRequestError("AI provider returned an empty reply")
        return answer.strip()
    except ProviderRequestError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderRequestError("AI provider request failed") from exc
