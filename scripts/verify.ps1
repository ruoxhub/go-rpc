param(
    [Parameter(Mandatory = $true)]
    [string]$ImpactAnalysisEvidence
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$tempGradleProjectCache = Join-Path ([IO.Path]::GetTempPath()) ("go-rpc-stage1-verify-gradle-project-" + [Guid]::NewGuid().ToString("N"))
$oldPythonNoBytecode = [Environment]::GetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "Process")
$oldGradleUserHome = [Environment]::GetEnvironmentVariable("GRADLE_USER_HOME", "Process")

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

try {
    New-Item -ItemType Directory -Path $tempGradleProjectCache -Force | Out-Null
    $env:PYTHONDONTWRITEBYTECODE = "1"
    if ($null -eq $oldGradleUserHome) {
        $env:GRADLE_USER_HOME = Join-Path ([IO.Path]::GetTempPath()) "go-rpc-stage1-gradle-home"
    }

    Invoke-Check "Go tests" { go test ./... }
    Invoke-Check "Core race tests" { go test -race ./pkg/client/... ./pkg/handler/... ./pkg/websocket/... }
    Invoke-Check "Frontend lint" { npm --prefix web run lint }
    Invoke-Check "Frontend build" { npm --prefix web run build }
    Invoke-Check "TypeScript SDK install" { npm --prefix sdk/typescript ci }
    Invoke-Check "TypeScript SDK test" { npm --prefix sdk/typescript test }
    Invoke-Check "Python SDK" { python -m unittest discover -s sdk/python/tests -v }
    Invoke-Check "Java SDK" { & .\sample\xposed\gradlew.bat -p sdk/java test jar --no-daemon --project-cache-dir $tempGradleProjectCache }
    Invoke-Check "Stage 1 conformance" { go run ./conformance/runner }
} finally {
    if ($null -eq $oldPythonNoBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue } else { $env:PYTHONDONTWRITEBYTECODE = $oldPythonNoBytecode }
    if ($null -eq $oldGradleUserHome) { Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue } else { $env:GRADLE_USER_HOME = $oldGradleUserHome }
    if (Test-Path -LiteralPath $tempGradleProjectCache) { Remove-Item -LiteralPath $tempGradleProjectCache -Recurse -Force }
}

Write-Host "All repository verification checks passed."
