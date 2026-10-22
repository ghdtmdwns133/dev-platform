# Bootstrap a dev-platform checkout on Windows.
# Detects required tools, prints install hints instead of installing anything,
# then syncs the CLI environment, checks the version contract and installs hooks.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $hints = @{
        uv     = "https://docs.astral.sh/uv/getting-started/installation/"
        node   = "https://nodejs.org/en/download"
        dotnet = "https://dotnet.microsoft.com/download"
        docker = "https://docs.docker.com/engine/install/"
    }
    $missing = @()
    foreach ($tool in @("uv", "node", "dotnet", "docker")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            $missing += $tool
        }
    }
    if ($missing.Count -gt 0) {
        Write-Host "Missing required tools: $($missing -join ', ')"
        foreach ($tool in $missing) {
            Write-Host "  install $tool`: $($hints[$tool])"
        }
        Write-Host "Install them and re-run scripts/bootstrap.ps1 (nothing was installed automatically)."
        exit 1
    }

    & uv sync --project cli
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & uv run --project cli devctl versions --check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & uv run --project cli devctl hooks install
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
