import json

import httpx
import pytest
from devops_ci.deepseek import DeepSeekClient, DeepSeekConfig, DeepSeekError


def test_deepseek_client_uses_json_mode_and_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-chat"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["temperature"] == 0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    assert client.smoke_test() == {"status": "ok"}


def test_deepseek_client_sanitizes_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid test-key")

    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DeepSeekError) as error:
        client.smoke_test()
    assert "test-key" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_deepseek_client_rejects_non_json_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DeepSeekError, match="invalid JSON"):
        client.smoke_test()
