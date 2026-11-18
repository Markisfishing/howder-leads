param(
    [ValidateSet("all", "api", "worker", "frontend")]
    [string]$Service = "all",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "找不到 $Name。請先安裝並確認它已加入 PATH。"
    }
}

function Test-ListeningPort {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Invoke-ChildService {
    param([string]$Name)

    switch ($Name) {
        "api" {
            Set-Location (Join-Path $Root "backend")
            Write-Host "啟動後端 API：http://127.0.0.1:8000"
            & uv run uvicorn app.main:app --reload --port 8000
        }
        "worker" {
            Set-Location (Join-Path $Root "backend")
            Write-Host "啟動背景 Worker"
            & uv run python -m app.workers
        }
        "frontend" {
            Set-Location (Join-Path $Root "frontend")
            Write-Host "啟動前端：http://127.0.0.1:5173"
            & npm run dev
        }
    }
    exit $LASTEXITCODE
}

if ($Service -ne "all") {
    Require-Command "uv"
    if ($Service -eq "frontend") { Require-Command "npm" }
    Invoke-ChildService $Service
}

Require-Command "docker"
Require-Command "uv"
Require-Command "npm"

$backend = Join-Path $Root "backend"
$frontend = Join-Path $Root "frontend"
$envFile = Join-Path $backend ".env"

if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    $envText = Get-Content -Raw $envFile
    $envText = $envText -replace "(?m)^DATABASE_URL=.*$", "DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/howder"
    [System.IO.File]::WriteAllText($envFile, $envText, [System.Text.UTF8Encoding]::new($false))
    Write-Host "已建立 backend\.env（開發用 Docker PostgreSQL 設定）" -ForegroundColor Yellow
}

# 一鍵模式固定使用本腳本啟動的 Docker PostgreSQL；不覆蓋既有 .env。
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/howder"

Write-Host "啟動 PostgreSQL..." -ForegroundColor Cyan
Set-Location $Root
& docker compose up -d postgres
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 啟動失敗。" }

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    & docker compose exec -T postgres pg_isready -U postgres -d howder 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "PostgreSQL 等待逾時，請執行 docker compose logs postgres 查看原因。" }

Write-Host "同步後端套件與資料庫..." -ForegroundColor Cyan
Set-Location $backend
& uv sync
if ($LASTEXITCODE -ne 0) { throw "後端套件同步失敗。" }
& uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "資料庫 migration 失敗。" }
& uv run python -m scripts.seed_templates
if ($LASTEXITCODE -ne 0) { throw "初版郵件模板建立失敗。" }

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "第一次啟動，安裝前端套件..." -ForegroundColor Cyan
    Set-Location $frontend
    & npm install
    if ($LASTEXITCODE -ne 0) { throw "前端套件安裝失敗。" }
}

Set-Location $Root
if (Test-ListeningPort 8000) {
    Write-Host "API 已在 8000 執行，略過重複啟動。" -ForegroundColor Yellow
} else {
    Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Service", "api"
    )
}

Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Service", "worker"
)

if (Test-ListeningPort 5173) {
    Write-Host "前端已在 5173 執行，略過重複啟動。" -ForegroundColor Yellow
} else {
    Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Service", "frontend"
    )
}

if (-not $NoBrowser) {
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { break }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Start-Process "http://127.0.0.1:5173"
}

Write-Host "" 
Write-Host "開發環境已啟動" -ForegroundColor Green
Write-Host "Web：    http://127.0.0.1:5173"
Write-Host "API：    http://127.0.0.1:8000"
Write-Host "Health： http://127.0.0.1:8000/health"
Write-Host "停止 PostgreSQL：docker compose down"
