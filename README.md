# 厚達電子業務推薦系統

## 一鍵啟動開發環境

在專案根目錄開啟 PowerShell，執行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

啟動腳本會依序完成：

1. 檢查 Docker 引擎；沒開的話自動啟動 Docker Desktop，最多等 120 秒（Docker Desktop 不在預設位置時，用環境變數 `HOWDER_DOCKER_DESKTOP` 指定 `Docker Desktop.exe` 的路徑），再啟動 Docker PostgreSQL。
2. 第一次使用時建立 `backend/.env`，不會覆蓋既有設定。
   一鍵模式會在目前啟動程序中使用 Docker 的 `127.0.0.1:5432`，不會改寫既有 `.env` 的資料庫設定。
3. 同步後端套件。
4. 套用資料庫 migration。
5. 建立初版郵件模板。
6. 第一次使用時安裝前端套件。
7. 分別開啟後端 API、背景 Worker 與前端 Web。
8. 啟動本機 Ollama（如果尚未執行）。
9. 自動開啟瀏覽器。

啟動完成後：

```text
Web：    http://127.0.0.1:5173
API：    http://127.0.0.1:8000
Health： http://127.0.0.1:8000/health
```

開發模式預設使用 Email 登入，寄信模式是 `sandbox`，不會真的寄出郵件。
官網摘要與 AI 草稿預設使用本機 Ollama 的 `qwen3:8b`；請先確認模型已安裝：

```powershell
ollama pull qwen3:8b
```

這台開發機若使用自訂模型位置，腳本會自動使用 `C:\howder-wt\ollama-home` 與 `D:\ollama\models`。其他電腦可先設定：

```powershell
$env:HOWDER_OLLAMA_USERPROFILE = "C:\你的 Ollama home"
$env:HOWDER_OLLAMA_MODELS = "D:\你的模型資料夾"
```

若只想啟動 Web、API 與 Worker，不啟動 Ollama：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -NoOllama
```

## 停止環境

關閉由腳本開啟的 API、Worker 與前端 PowerShell 視窗後，在專案根目錄執行：

```powershell
docker compose down
```

這只會停止並移除 PostgreSQL 容器，不會刪除 Docker volume 中的資料。

## 個別啟動服務

如果只需要啟動某一個服務：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -Service api
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -Service worker
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -Service frontend
```

不想自動開啟瀏覽器時：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -NoBrowser
```

## Docker 不可用時

可以改用內嵌 PostgreSQL。先在一個 PowerShell 視窗執行：

```powershell
cd backend
uv run python -m scripts.dev_db
```

接著依畫面印出的 `DATABASE_URL` 更新 `backend/.env`，再分別啟動 API、Worker 與前端。

## 需要的工具

- Docker Desktop
- Python 3.12
- `uv`
- Node.js 與 npm
