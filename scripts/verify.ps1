param(
    [Parameter(Mandatory = $true)]
    [string]$ImpactAnalysisEvidence
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

if ([string]::IsNullOrWhiteSpace($ImpactAnalysisEvidence)) {
    throw "Record the GitNexus change-detection result, or the manual review used when GitNexus is unavailable."
}
Write-Host "==> Impact analysis evidence: $ImpactAnalysisEvidence"

Invoke-Check "Go tests" { go test ./... }
Invoke-Check "Core race tests" { go test -race ./pkg/client/... ./pkg/handler/... ./pkg/websocket/... }
Invoke-Check "Frontend lint" { npm --prefix web run lint }
Invoke-Check "Frontend build" { npm --prefix web run build }

Write-Host "All repository verification checks passed."
