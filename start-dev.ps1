param(
    [ValidateSet("all", "api", "worker", "frontend")]
    [string]$Service = "all",
    [switch]$NoBrowser,
    [switch]$NoOllama
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

function Get-ConfiguredPath {
    param(
        [string]$EnvironmentName,
        [string]$FallbackPath
    )

    $configured = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return $configured
    }
    if (Test-Path $FallbackPath) {
        return $FallbackPath
    }
    return $null
}

function Test-OllamaReady {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function Quote-PowerShellLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Start-Ollama {
    if (Test-OllamaReady) {
        Write-Host "Ollama 已在 11434 執行，略過重複啟動。" -ForegroundColor Yellow
        return
    }

    Require-Command "ollama"

    # 這台開發機的 Ollama home 與模型路徑需要避開失效的 .ollama 符號連結。
    # 其他電腦可用 HOWDER_OLLAMA_USERPROFILE／HOWDER_OLLAMA_MODELS 覆寫，或直接使用預設路徑。
    $ollamaUserProfile = Get-ConfiguredPath "HOWDER_OLLAMA_USERPROFILE" "C:\howder-wt\ollama-home"
    $ollamaModels = Get-ConfiguredPath "HOWDER_OLLAMA_MODELS" "D:\ollama\models"
    $commandLines = @()
    if ($null -ne $ollamaUserProfile) {
        $commandLines += "$" + "env:USERPROFILE = $(Quote-PowerShellLiteral $ollamaUserProfile)"
    }
    if ($null -ne $ollamaModels) {
        $commandLines += "$" + "env:OLLAMA_MODELS = $(Quote-PowerShellLiteral $ollamaModels)"
    }
    $commandLines += "ollama serve"
    $ollamaCommand = $commandLines -join "`r`n"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($ollamaCommand))

    Write-Host "啟動 Ollama：http://127.0.0.1:11434" -ForegroundColor Cyan
    Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand
    )

    for ($i = 0; $i -lt 30; $i++) {
        if (Test-OllamaReady) {
            Write-Host "Ollama 已就緒。" -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Ollama 啟動逾時。請確認 ollama serve 視窗沒有錯誤，或使用 -NoOllama 略過。"
}

function Test-DockerReady {
    # docker 引擎沒開時會寫 stderr；PowerShell 5.1 在 Stop 模式下會把它當成例外，這裡暫時放寬。
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker info --format "{{.ServerVersion}}" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Test-PostgresReady {
    # PostgreSQL 還沒好時 docker compose exec 會寫 stderr；理由同 Test-DockerReady。
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker compose exec -T postgres pg_isready -U postgres -d howder *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Start-DockerEngine {
    if (Test-DockerReady) {
        return
    }

    # 其他電腦可用 HOWDER_DOCKER_DESKTOP 指定 Docker Desktop.exe 的位置。
    $dockerDesktop = Get-ConfiguredPath "HOWDER_DOCKER_DESKTOP" (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
    if ($null -eq $dockerDesktop -or -not (Test-Path $dockerDesktop)) {
        throw "Docker 引擎沒有在執行，也找不到 Docker Desktop。請手動啟動 Docker，或設定 HOWDER_DOCKER_DESKTOP 指向 Docker Desktop.exe。"
    }

    Write-Host "Docker 引擎沒有在執行，正在啟動 Docker Desktop（第一次可能要一兩分鐘）..." -ForegroundColor Cyan
    Start-Process $dockerDesktop

    for ($i = 0; $i -lt 120; $i++) {
        if (Test-DockerReady) {
            Write-Host "Docker 已就緒。" -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Docker Desktop 啟動逾時（120 秒）。請確認 Docker Desktop 視窗沒有錯誤後再重新執行。"
}

function Invoke-ChildService {
    param([string]$Name)

    switch ($Name) {
        "api" {
            Set-Location (Join-Path $Root "backend")
            Write-Host "啟動後端 API：http://127.0.0.1:8000"
            & uv run python -m uvicorn app.main:app --reload --port 8000
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

Start-DockerEngine

if (-not $NoOllama) {
    Start-Ollama
} else {
    Write-Host "略過 Ollama 啟動（-NoOllama）；官網摘要與 AI 寫信暫時不可用。" -ForegroundColor Yellow
}

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
    if (Test-PostgresReady) {
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
# uv 的 .exe 啟動器（trampoline）在中文路徑下會失敗，一律用 python -m 執行。
& uv run python -m alembic upgrade head
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
