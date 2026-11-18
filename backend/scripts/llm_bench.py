"""本機 LLM 速度與失敗率實測（M4-06b、M4-06l、ADR 0006）：手動執行，不進 pytest。

用 N 家「假公司」（只有公司層級資料）依 LLM_CONCURRENCY 同時產生，印出總耗時、每封秒數與失敗原因。
對照 SPEC F-MAIL-3：50 封草稿 3 分鐘內產生完。

用法（先啟動 Ollama）：
    cd backend
    uv run python -m scripts.llm_bench --n 50 --concurrency 2
    uv run python -m scripts.llm_bench --model qwen3:14b --n 10 --mode full_ai
"""

import argparse
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.domain.company_rules import DomainError
from app.services import ai_writer
from app.services.llm import LlmError, LocalLlmClient

# 假公司資料：名稱、產業與描述都是虛構的，輪流使用
_INDUSTRIES = [
    ("工業自動化與機械設備", "包裝機械、PLC 控制盤", "整機含控制箱與 PLC，端子台用量大"),
    ("配電盤與電機控制", "低壓配電盤", "自製配電盤，需要大量端子台"),
    ("電子連接器、線材與 EMS", "線束組裝", "線束與盤內配線工序多"),
    ("馬達、變壓器與電力設備", "小型馬達", "部分機型有電控箱"),
    ("金屬、模具與塑膠零件製造", "塑膠射出零件", "多為零件加工，端子台需求不明確"),
]


def brief_for(i: int) -> ai_writer.Brief:
    industry, product, reason = _INDUSTRIES[i % len(_INDUSTRIES)]
    return ai_writer.Brief(
        company_name=f"範例公司{i + 1:03d}股份有限公司",
        industry=industry,
        product_type=product,
        reason=reason,
        contact_name="採購負責人",
        sender_name="王小明",
    )


def one(client: LocalLlmClient, mode: str, i: int) -> tuple[float, str | None]:
    started = time.monotonic()
    try:
        if mode == "template_ai":
            ai_writer.write_paragraph(client, brief_for(i))
        else:
            ai_writer.write_mail(client, brief_for(i))
    except (LlmError, DomainError) as e:
        return time.monotonic() - started, e.code
    return time.monotonic() - started, None


def main() -> int:
    parser = argparse.ArgumentParser(description="本機 LLM 速度與失敗率實測")
    parser.add_argument("--mode", choices=["template_ai", "full_ai"], default="template_ai")
    parser.add_argument("--model")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.local_llm_model
    workers = args.concurrency or settings.llm_concurrency
    client = LocalLlmClient(settings.local_llm_base_url, model, settings.llm_timeout_seconds)
    print(f"模型 {model}｜模式 {args.mode}｜{args.n} 封｜並發 {workers}｜prompt {ai_writer.PROMPT_VERSION}")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda i: one(client, args.mode, i), range(args.n)))
    total = time.monotonic() - started
    times = sorted(t for t, _ in results)
    failures = Counter(code for _, code in results if code)
    print(f"總耗時 {total:.0f} 秒（{total / args.n:.1f} 秒/封，F-MAIL-3 目標：50 封 180 秒內）")
    print(f"每封：中位數 {statistics.median(times):.1f}、最慢 {times[-1]:.1f} 秒（含首封載入模型的冷啟動）")
    print(f"失敗 {sum(failures.values())}/{args.n}（每封內建重試一次）{dict(failures) or ''}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
