# 0006 AI 寫信先用地端 LLM 試，Claude 保留為可切換的選項

- 日期：2026-11-17
- 狀態：採用（試行；M4-06b 的比較結果出來後再確認）
- 相關：SPEC 7.4、M4-06、M4-08、CLAUDE.md 第 4 節第 5 點、第 6 節

## 背景
SPEC 7.4 原本規劃用 Claude API 產生郵件內容。使用者決定 M4 先用**地端 LLM** 試：公司名單、推薦理由、官網摘要不送到外部服務，而且沒有逐次的 API 費用。

但地端模型有幾個風險要先驗證：
- 繁體中文商業書信的品質，以及會不會混入簡體字。
- 能不能穩定回傳指定的 JSON 格式。
- 速度：SPEC 要求 50 封草稿 3 分鐘內產生完，要看機器有沒有 GPU。
- 會不會捏造實績、價格、認證（CLAUDE.md 第 6 節第 6 點）。

## 決定
1. `services/generator` 定義一個 `LlmClient` 介面（輸入 system prompt＋公司資料，輸出 JSON 字串），有三種實作：
   - `LocalLlmClient`：呼叫 **OpenAI 相容的 HTTP API**（`/v1/chat/completions`）。Ollama、LM Studio、vLLM、llama.cpp server 都提供這個介面，換執行環境只要改網址，不用改程式。
   - `ClaudeClient`：保留原本規劃，之後要比較或切換時使用。
   - `FakeLlmClient`：測試專用。
2. 用環境變數切換：`LLM_PROVIDER=local|claude`（預設 `local`）、`LOCAL_LLM_BASE_URL`、`LOCAL_LLM_MODEL`、`LLM_CONCURRENCY`。
3. 不管用哪一種，同一套規則都適用：
   - prompt 放在 `backend/app/prompts/`，檔名帶版本。
   - 回傳的 JSON 一律驗證欄位與長度，不合格就算這封失敗，可以重新產生。
   - 加一道**簡體字檢查**：出現常見簡體字就標記失敗並重試一次，不自動轉換，避免改壞用詞。
   - 草稿記錄是哪個 provider、哪個模型、哪一版 prompt 產生的，才能比較品質。
4. 自動化測試不連真實的地端 LLM，也不連 Claude（和 Graph 一樣用假的實作）。
5. 選模型的方式（M4-06b）：挑 2～3 個繁中能力好的開源模型，用同一批 10 家公司產生草稿，請業務盲評：通順度、正確性、有沒有捏造、要改多少。記錄速度與硬體需求，結果寫回這份 ADR。

## 理由
- 資料不出公司，對個資與客戶名單比較安全。
- 用 OpenAI 相容介面，執行環境和模型都能換，不會綁死在某一套軟體上。
- 保留 Claude 實作，地端品質不夠時只要改設定就能切回去，不用重寫流程。

## 代價
- 要有一台能跑模型的機器（最好有 GPU），而且要有人維護。
- 地端模型的品質與 JSON 穩定度通常不如 Claude，要多做驗證與重試。
- Claude 的 prompt caching 用不到；地端的速度取決於硬體。
