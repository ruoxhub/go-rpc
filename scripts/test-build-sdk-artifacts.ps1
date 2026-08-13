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

Write-Host "Artifact output path safety checks passed."
