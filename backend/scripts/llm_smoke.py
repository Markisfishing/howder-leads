"""本機 LLM 冒煙測試（M4-06g、ADR 0006）：手動執行，不進 pytest。

用 1 家假公司（只有公司層級資料，沒有任何聯絡人個資）對設定的 LLM 產生一次，印出：
耗時、token 數、JSON 是否合格、有沒有簡體字、產生的內容。

用法（先啟動 Ollama：`ollama serve`，模型在 D:\\ollama\\models）：
    cd backend
    uv run python -m scripts.llm_smoke                      # template_ai，用 .env 的模型
    uv run python -m scripts.llm_smoke --mode full_ai
    uv run python -m scripts.llm_smoke --model qwen3:14b --runs 3
"""

import argparse
import sys

from app.config import get_settings
from app.domain.company_rules import DomainError
from app.services import ai_writer
from app.services.llm import LlmError, LocalLlmClient

# 假公司：名稱與描述都是虛構的
BRIEF = ai_writer.Brief(
    company_name="範例自動化股份有限公司",
    industry="工業自動化與機械設備",
    product_type="包裝機械、PLC 控制盤",
    reason="整機含控制箱與 PLC，端子台用量大",
    contact_name="採購負責人",
    sender_name="王小明",
)


def run_once(client: LocalLlmClient, mode: str) -> bool:
    request_fn = ai_writer.write_paragraph if mode == "template_ai" else ai_writer.write_mail
    try:
        parsed, result = request_fn(client, BRIEF)
    except (LlmError, DomainError) as e:
        print(f"  失敗：{e.code}")
        return False
    tokens = f"{result.prompt_tokens}/{result.completion_tokens}" if result.completion_tokens is not None else "?"
    print(f"  耗時 {result.seconds:.1f} 秒｜token（輸入/輸出）{tokens}｜JSON 合格、無簡體字")
    if mode == "template_ai":
        print(f"  段落：{parsed.ai_paragraph}")  # type: ignore[union-attr]
    else:
        print(f"  主旨：{parsed.subject}\n  內文：\n{parsed.body_text}")  # type: ignore[union-attr]
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="本機 LLM 冒煙測試")
    parser.add_argument("--mode", choices=["template_ai", "full_ai"], default="template_ai")
    parser.add_argument("--model", help="覆蓋 LOCAL_LLM_MODEL")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.local_llm_model
    client = LocalLlmClient(settings.local_llm_base_url, model, settings.llm_timeout_seconds)
    print(f"LLM：{settings.local_llm_base_url}　模型：{model}　模式：{args.mode}　prompt：{ai_writer.PROMPT_VERSION}")
    ok = sum(run_once(client, args.mode) for _ in range(args.runs))
    print(f"完成：{ok}/{args.runs} 次合格（每次內建重試一次）")
    return 0 if ok == args.runs else 1


if __name__ == "__main__":
    sys.exit(main())
