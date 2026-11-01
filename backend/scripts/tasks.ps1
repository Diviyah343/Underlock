param(
    [Parameter(Position = 0)]
    [string]$Task = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TaskArgs = @()
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Invoke-IntegrationTests {
    Invoke-External "docker" @("compose", "up", "-d", "--wait")
    Invoke-External "uv" @("run", "alembic", "upgrade", "head")
    Invoke-External "uv" @("run", "python", "-m", "api.seed")
    Invoke-External "uv" @("run", "pytest", "-m", "integration", "-q")
}

switch ($Task.ToLowerInvariant()) {
    "help" {
        Write-Output "Usage: .\scripts\tasks.ps1 <up|down|migrate|seed|api|worker|sim|test|test-integration|bench|preflight|lint|scoring|openapi> [arguments]"
    }
    "up" { Invoke-External "docker" @("compose", "up", "-d", "--wait") }
    "down" { Invoke-External "docker" @("compose", "down") }
    "migrate" { Invoke-External "uv" @("run", "alembic", "upgrade", "head") }
    "seed" { Invoke-External "uv" @("run", "python", "-m", "api.seed") }
    "api" { Invoke-External "uv" @("run", "uvicorn", "api.main:app", "--reload") }
    "run" { Invoke-External "uv" @("run", "uvicorn", "api.main:app", "--reload") }
    "worker" { Invoke-External "uv" @("run", "python", "-m", "worker.main") }
    "run-worker" { Invoke-External "uv" @("run", "python", "-m", "worker.main") }
    "sim" { Invoke-External "uv" (@("run", "python", "-m", "simulator") + $TaskArgs) }
    "simulate" { Invoke-External "uv" (@("run", "python", "-m", "simulator") + $TaskArgs) }
    "test" { Invoke-External "uv" @("run", "pytest") }
    "test-integration" { Invoke-IntegrationTests }
    "bench" {
        Invoke-External "uv" (@("run", "python", "scripts/bench_ingest.py", "--confirm-clean") + $TaskArgs)
    }
    "benchmark" {
        Invoke-External "uv" (@("run", "python", "scripts/bench_ingest.py", "--confirm-clean") + $TaskArgs)
    }
    "preflight" { Invoke-External "uv" @("run", "python", "scripts/preflight.py") }
    "lint" {
        Invoke-External "uv" @("run", "ruff", "check", "api", "shared", "worker", "scoring", "simulator", "scripts")
        Invoke-External "uv" @("run", "mypy", "api", "shared", "worker", "scoring", "simulator", "scripts")
    }
    "run-scoring" { Invoke-External "uv" @("run", "uvicorn", "scoring.main:app", "--reload", "--port", "8001") }
    "scoring" { Invoke-External "uv" @("run", "uvicorn", "scoring.main:app", "--reload", "--port", "8001") }
    "openapi" { Invoke-External "uv" @("run", "python", "scripts/export_openapi.py") }
    default { throw "Unknown task '$Task'. Run .\scripts\tasks.ps1 help for available tasks." }
}