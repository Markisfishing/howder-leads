"""LLM 呼叫（M4-06a、M4-06f、ADR 0006）。

- LlmClient：輸入 system prompt 與使用者內容，回傳文字、耗時、token 數。
- LocalLlmClient：呼叫 OpenAI 相容的 /v1/chat/completions（Ollama、LM Studio、vLLM…）。
- FakeLlmClient：測試專用，不連任何服務（CLAUDE.md 第 6 節第 4 點）。
log 只記模型、耗時、token 數與錯誤代碼，不記 prompt 或回覆內容（CLAUDE.md 第 8 節第 4 點）。
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger("howder.llm")


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    json_mode: bool = True
    temperature: float = 0.4


@dataclass(frozen=True)
class LlmResult:
    text: str
    provider: str
    model: str
    seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LlmError(Exception):
    """呼叫失敗。code 給前端對應中文訊息；retryable=True 代表值得再試一次（逾時、暫時連不上）。"""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LlmClient(Protocol):
    provider: str
    model: str

    def complete(self, request: LlmRequest) -> LlmResult: ...


class FakeLlmClient:
    """測試用：依序回傳預先放好的文字；放 LlmError 實例代表那一次要失敗。"""

    provider = "fake"
    model = "fake-model"

    def __init__(self, replies: list[str | LlmError] | Callable[[LlmRequest], str] | None = None) -> None:
        self._replies = replies if replies is not None else []
        self.requests: list[LlmRequest] = []

    def complete(self, request: LlmRequest) -> LlmResult:
        self.requests.append(request)
        if callable(self._replies):
            text: str | LlmError = self._replies(request)
        elif self._replies:
            text = self._replies.pop(0)
        else:
            raise LlmError("LLM_UNAVAILABLE", retryable=False)
        if isinstance(text, LlmError):
            raise text
        return LlmResult(text=text, provider=self.provider, model=self.model, seconds=0.0)


class LocalLlmClient:
    """OpenAI 相容的本機／內網 LLM（預設 Ollama）。qwen3 的思考模式關掉，省時間也避免 <think> 混進回覆。"""

    provider = "local"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport)

    def complete(self, request: LlmRequest) -> LlmResult:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "stream": False,
            # Ollama 的 OpenAI 相容端點：關閉 qwen3 思考模式（其他伺服器會忽略這個欄位）
            "think": False,
            "reasoning_effort": "none",
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        try:
            res = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as e:
            log.warning("LLM 逾時 model=%s", self.model)
            raise LlmError("LLM_TIMEOUT", retryable=True) from e
        except httpx.HTTPError as e:
            log.warning("LLM 連不上 model=%s error=%s", self.model, type(e).__name__)
            raise LlmError("LLM_UNAVAILABLE", retryable=True) from e
        seconds = time.monotonic() - started
        if res.status_code >= 500 or res.status_code == 429:
            raise LlmError("LLM_UNAVAILABLE", retryable=True)
        if res.status_code >= 400:
            log.warning("LLM 回 %s model=%s", res.status_code, self.model)
            raise LlmError("LLM_BAD_REQUEST")
        try:
            data = res.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LlmError("LLM_BAD_RESPONSE", retryable=True) from e
        if not isinstance(text, str) or not text.strip():
            raise LlmError("LLM_BAD_RESPONSE", retryable=True)
        usage = data.get("usage") or {}
        log.info("LLM 完成 model=%s seconds=%.1f", self.model, seconds)
        return LlmResult(
            text=text,
            provider=self.provider,
            model=self.model,
            seconds=seconds,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


def get_llm_client(settings: Settings) -> LlmClient:
    """依設定建立 client（ADR 0006）。claude 要等 M4-06d；先明確報錯，不默默改用別的。

    自動化測試（ENV=test）一律不准建立真實 client：測試要自己注入 FakeLlmClient（CLAUDE.md 第 6 節第 4 點）。
    """
    if settings.env == "test":
        raise LlmError("LLM_DISABLED_IN_TEST")
    if settings.llm_provider == "local":
        return LocalLlmClient(settings.local_llm_base_url, settings.local_llm_model, settings.llm_timeout_seconds)
    raise LlmError("LLM_PROVIDER_NOT_AVAILABLE")
