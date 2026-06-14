# EP2737 production report build (no venv activation required).
# Usage from repo root:
#   .\scripts\run_ep2737_report.ps1
#   .\scripts\run_ep2737_report.ps1 -ValidateOnly

param(
    [switch]$ValidateOnly,
    [switch]$NoPdf,
    [switch]$WithImages,
    [string]$OutDir = "automated_scripts_output"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Cli = Join-Path $RepoRoot ".venv\Scripts\ansys-report.exe"
$Config = Join-Path $RepoRoot "config\project.ep2737.production.yaml"
$CaseRoot = Join-Path $RepoRoot "ansys_automation_files"

if (-not (Test-Path $Python)) {
    Write-Error @"
Python venv not found. From repo root run:
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -e .
"@
    exit 1
}

if (-not (Test-Path $Cli)) {
    Write-Host "Installing ansys-report into .venv ..."
    & $Python -m pip install -e .
    if (-not (Test-Path $Cli)) {
        Write-Error "ansys-report CLI missing after install."
        exit 1
    }
}

$env:EP2737_CASE_ROOT = $CaseRoot
$env:PYTHONIOENCODING = "utf-8"

$args = @(
    "--config", $Config,
    "--out", $OutDir
)

if ($WithImages) {
    $args += "--image-map", (Join-Path $RepoRoot "config\ep2737_image_map.yaml")
}

if ($ValidateOnly) {
    $args = @("validate") + $args + @("--verbose")
} else {
    $args = @("build") + $args
    if ($NoPdf) { $args += "--no-pdf" }
}

Write-Host "EP2737_CASE_ROOT=$env:EP2737_CASE_ROOT"
Write-Host "Running: $Cli $($args -join ' ')"

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Cli @args
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
exit $exitCode
