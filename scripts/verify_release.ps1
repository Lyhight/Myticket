[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipFrontend,
    [switch]$DockerConfig,
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$windowsPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$unixPython = Join-Path $backendRoot ".venv/bin/python"

if ($PythonExecutable) {
    if (-not (Test-Path -LiteralPath $PythonExecutable)) {
        throw "Python executable does not exist: $PythonExecutable"
    }
    $python = (Resolve-Path -LiteralPath $PythonExecutable).Path
} elseif (Test-Path -LiteralPath $windowsPython) {
    $python = $windowsPython
} elseif (Test-Path -LiteralPath $unixPython) {
    $python = $unixPython
} else {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = $pythonCommand.Source
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)] [string]$Label,
        [Parameter(Mandatory)] [string]$WorkingDirectory,
        [Parameter(Mandatory)] [string]$Executable,
        [Parameter(Mandatory)] [string[]]$CommandArguments
    )

    Write-Host "`n==> $Label" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        & $Executable @CommandArguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Label failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Invoke-Checked "Validate project configuration" $backendRoot $python @(
    "validate_project_config.py"
)
Invoke-Checked "Check Python dependencies" $backendRoot $python @(
    "-m", "pip", "check"
)
Invoke-Checked "Check Alembic migration head" $backendRoot $python @(
    "-m", "alembic", "heads"
)

if (-not $SkipTests) {
    Invoke-Checked "Run backend tests" $backendRoot $python @(
        "-m", "pytest", "-q"
    )
}

$verificationReport = Join-Path $projectRoot "benchmark\reports\verification"
Invoke-Checked "Run offline benchmark" $backendRoot $python @(
    "run_benchmark.py", "--skip-rag", "--output", $verificationReport
)
Invoke-Checked "Apply offline quality gate" $backendRoot $python @(
    "run_quality_gate.py",
    "--skip-rag",
    "--output",
    (Join-Path $verificationReport "quality-gate.json")
)

if (-not $SkipFrontend) {
    $npm = (Get-Command npm -ErrorAction Stop).Source
    Invoke-Checked "Build frontend" $frontendRoot $npm @("run", "build")
}

if ($DockerConfig) {
    $docker = (Get-Command docker -ErrorAction Stop).Source
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env"))) {
        throw "Docker validation requires .env. Copy .env.compose.example to .env first."
    }
    Invoke-Checked "Validate Docker Compose" $projectRoot $docker @(
        "compose", "--profile", "monitoring", "config", "--quiet"
    )
}

Write-Host "`nRelease verification passed." -ForegroundColor Green
Write-Host "Offline report: $verificationReport"
if (-not $DockerConfig) {
    Write-Host "Docker validation was not requested; add -DockerConfig when Docker is available."
}
