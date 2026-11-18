"""LLM 呼叫層（M4-06a、M4-06f、ADR 0006）。一律用假的 HTTP 回應，不連本機 Ollama 也不連 Claude。"""

import json

import httpx
import pytest

from app.config import Settings
from app.services.llm import ClaudeClient, FakeLlmClient, LlmError, LlmRequest, LocalLlmClient, get_llm_client

REQ = LlmRequest(system="你是業務助理", user="公司：測試公司")


def _client(handler: httpx.MockTransport) -> LocalLlmClient:
    return LocalLlmClient("http://llm.example.com/v1", "qwen3:8b", 5.0, transport=handler)


def _ok(content: str = '{"ai_paragraph": "x"}') -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            },
        )

    return httpx.MockTransport(handler)


def test_m4_06f_local_client_posts_openai_compatible_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    result = _client(httpx.MockTransport(handler)).complete(REQ)
    assert seen["url"] == "http://llm.example.com/v1/chat/completions"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3:8b"
    assert body["messages"] == [
        {"role": "system", "content": "你是業務助理"},
        {"role": "user", "content": "公司：測試公司"},
    ]
    assert body["response_format"] == {"type": "json_object"}
    assert body["think"] is False  # 關閉 qwen3 思考模式
    assert body["stream"] is False
    assert result.text == "ok"
    assert (result.provider, result.model) == ("local", "qwen3:8b")


def test_m4_06f_local_client_reports_tokens_and_seconds() -> None:
    result = _client(_ok()).complete(REQ)
    assert (result.prompt_tokens, result.completion_tokens) == (12, 34)
    assert result.seconds >= 0


def test_m4_06f_json_mode_can_be_turned_off() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "文字"}}]})

    _client(httpx.MockTransport(handler)).complete(LlmRequest(system="s", user="u", json_mode=False))
    assert "response_format" not in seen


@pytest.mark.parametrize(
    ("handler", "code", "retryable"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "LLM_UNAVAILABLE", True),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "LLM_TIMEOUT", True),
        (lambda r: httpx.Response(503), "LLM_UNAVAILABLE", True),
        (lambda r: httpx.Response(429), "LLM_UNAVAILABLE", True),
        (lambda r: httpx.Response(404, json={"error": "model not found"}), "LLM_BAD_REQUEST", False),
        (lambda r: httpx.Response(200, text="不是 JSON"), "LLM_BAD_RESPONSE", True),
        (lambda r: httpx.Response(200, json={"choices": []}), "LLM_BAD_RESPONSE", True),
        (lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}), "LLM_BAD_RESPONSE", True),
    ],
)
def test_m4_06f_local_client_maps_failures_to_error_codes(handler, code: str, retryable: bool) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(LlmError) as e:
        _client(httpx.MockTransport(handler)).complete(REQ)
    assert (e.value.code, e.value.retryable) == (code, retryable)


def test_m4_06a_fake_client_returns_replies_in_order_and_records_requests() -> None:
    fake = FakeLlmClient(["第一次", "第二次"])
    assert fake.complete(REQ).text == "第一次"
    assert fake.complete(REQ).text == "第二次"
    assert len(fake.requests) == 2
    with pytest.raises(LlmError):  # 沒有預先放好的回覆就當作連不上
        fake.complete(REQ)


def test_m4_06a_fake_client_can_fail_on_demand() -> None:
    fake = FakeLlmClient([LlmError("LLM_TIMEOUT", retryable=True), "好了"])
    with pytest.raises(LlmError) as e:
        fake.complete(REQ)
    assert e.value.code == "LLM_TIMEOUT"
    assert fake.complete(REQ).text == "好了"


def test_m4_06a_settings_default_to_local_ollama_and_inject_client() -> None:
    s = Settings(_env_file=None, env="development")
    assert s.llm_provider == "local"
    assert s.local_llm_base_url == "http://127.0.0.1:11434/v1"
    assert s.local_llm_model == "qwen3:8b"
    client = get_llm_client(Settings(_env_file=None, env="development", local_llm_model="qwen3:14b"))
    assert isinstance(client, LocalLlmClient)
    assert client.model == "qwen3:14b"


def test_m4_06d_claude_provider_needs_api_key_and_injects_client() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, env="development", llm_provider="claude")
    client = get_llm_client(Settings(_env_file=None, env="development", llm_provider="claude", anthropic_api_key="k"))
    assert isinstance(client, ClaudeClient) and client.model == "claude-sonnet-5-5"


def _claude(handler: httpx.MockTransport) -> ClaudeClient:
    return ClaudeClient("test-key", "claude-test", 5.0, transport=handler)


def test_m4_06d_claude_client_posts_messages_api_request_and_reads_text() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        seen["version"] = request.headers["anthropic-version"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"ai_paragraph": "x"}'}],
                "usage": {"input_tokens": 11, "output_tokens": 22},
            },
        )

    result = _claude(httpx.MockTransport(handler)).complete(REQ)
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert (seen["key"], seen["version"]) == ("test-key", "2023-06-01")
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["system"] == "你是業務助理" and body["messages"] == [{"role": "user", "content": "公司：測試公司"}]
    assert (result.text, result.provider, result.model) == ('{"ai_paragraph": "x"}', "claude", "claude-test")
    assert (result.prompt_tokens, result.completion_tokens) == (11, 22)


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(401), "LLM_AUTH_FAILED", False),
        (httpx.Response(403), "LLM_AUTH_FAILED", False),
        (httpx.Response(429), "LLM_UNAVAILABLE", True),
        (httpx.Response(529), "LLM_UNAVAILABLE", True),
        (httpx.Response(500), "LLM_UNAVAILABLE", True),
        (httpx.Response(400, json={"error": {}}), "LLM_BAD_REQUEST", False),
        (httpx.Response(200, json={"content": []}), "LLM_BAD_RESPONSE", True),
        (httpx.Response(200, text="不是 JSON"), "LLM_BAD_RESPONSE", True),
    ],
)
def test_m4_06d_claude_client_maps_failures_to_error_codes(
    response: httpx.Response, code: str, retryable: bool
) -> None:
    with pytest.raises(LlmError) as e:
        _claude(httpx.MockTransport(lambda r: response)).complete(REQ)
    assert (e.value.code, e.value.retryable) == (code, retryable)


@pytest.mark.parametrize("kwargs", [{"llm_concurrency": 0}, {"llm_timeout_seconds": 0}])
def test_m4_06a_settings_reject_bad_llm_values(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **kwargs)


def test_m4_06a_real_llm_client_is_refused_in_test_env() -> None:
    """ENV=test 時不准建立真實 client，避免自動化測試誤連本機 Ollama。"""
    with pytest.raises(LlmError) as e:
        get_llm_client(Settings(_env_file=None, env="test"))
    assert e.value.code == "LLM_DISABLED_IN_TEST"
