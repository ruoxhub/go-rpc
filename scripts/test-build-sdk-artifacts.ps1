$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "build-sdk-artifacts.ps1"
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "build-sdk-artifacts.ps1 is missing"
}

$invalidOutputDirectories = @(
    "artifacts",
    "artifacts/../outside",
    "..\outside",
    (Join-Path ([IO.Path]::GetPathRoot($PSScriptRoot)) "outside")
)

foreach ($outputDirectory in $invalidOutputDirectories) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -OutputDirectory $outputDirectory
    if ($LASTEXITCODE -eq 0) {
        throw "unsafe output directory was accepted: $outputDirectory"
    }
}

$artifactRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts"
$junctionName = "sdk-path-test-" + [Guid]::NewGuid().ToString("N")
$junctionPath = Join-Path $artifactRoot $junctionName
$externalPath = Join-Path ([IO.Path]::GetTempPath()) ("go-rpc-artifact-sentinel-" + [Guid]::NewGuid().ToString("N"))
$sentinelPath = Join-Path $externalPath "sentinel.txt"
try {
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $externalPath -Force | Out-Null
    Set-Content -LiteralPath $sentinelPath -Value "must survive" -NoNewline
    New-Item -ItemType Junction -Path $junctionPath -Target $externalPath -ErrorAction Stop | Out-Null

    $junctionOutput = Join-Path (Join-Path "artifacts" $junctionName) "sdk"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -OutputDirectory $junctionOutput
    if ($LASTEXITCODE -eq 0) {
        throw "reparse-point output directory was accepted: $junctionOutput"
    }
    if (-not (Test-Path -LiteralPath $sentinelPath -PathType Leaf)) {
        throw "reparse-point rejection removed the external sentinel"
    }
} finally {
    if (Test-Path -LiteralPath $junctionPath) { Remove-Item -LiteralPath $junctionPath -Recurse -Force -ErrorAction Stop }
    if (Test-Path -LiteralPath $externalPath) { Remove-Item -LiteralPath $externalPath -Recurse -Force }
}

Write-Host "Artifact output path safety checks passed."
