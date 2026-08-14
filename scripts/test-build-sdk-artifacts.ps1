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

$raceName = "sdk-toctou-" + [Guid]::NewGuid().ToString("N")
$raceOutput = Join-Path $artifactRoot $raceName
$raceExternal = Join-Path ([IO.Path]::GetTempPath()) ("go-rpc-toctou-" + [Guid]::NewGuid().ToString("N"))
$raceSentinel = Join-Path $raceExternal "sentinel.txt"
$marker = Join-Path ([IO.Path]::GetTempPath()) ($raceName + ".marker")
$release = Join-Path ([IO.Path]::GetTempPath()) ($raceName + ".release")
$process = $null
try {
    New-Item -ItemType Directory -Path $raceOutput -Force | Out-Null
    New-Item -ItemType Directory -Path $raceExternal -Force | Out-Null
    Set-Content -LiteralPath $raceSentinel -Value "must survive" -NoNewline
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -OutputDirectory artifacts/$raceName"
    $psi.WorkingDirectory = Split-Path -Parent $PSScriptRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardError = $true
    $psi.Environment["RPC_ARTIFACT_TEST_BEFORE_DELETE_MARKER"] = $marker
    $psi.Environment["RPC_ARTIFACT_TEST_BEFORE_DELETE_RELEASE"] = $release
    $process = [Diagnostics.Process]::Start($psi)
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $marker)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw "TOCTOU marker was not created" }
        Start-Sleep -Milliseconds 25
    }
    [IO.Directory]::Delete($raceOutput, $true)
    New-Item -ItemType Junction -Path $raceOutput -Target $raceExternal -ErrorAction Stop | Out-Null
    [IO.File]::WriteAllText($release, "release")
    $process.WaitForExit()
    $stderr = $process.StandardError.ReadToEnd()
    if ($process.ExitCode -eq 0) { throw "TOCTOU replacement was accepted" }
    if ($stderr -notmatch "reparse") { throw "TOCTOU rejection did not report a reparse point: $stderr" }
    if (-not (Test-Path -LiteralPath $raceSentinel -PathType Leaf)) { throw "TOCTOU rejection removed the external sentinel" }
} finally {
    if ($process -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    if (Test-Path -LiteralPath $raceOutput) { Remove-Item -LiteralPath $raceOutput -Recurse -Force }
    if (Test-Path -LiteralPath $raceExternal) { Remove-Item -LiteralPath $raceExternal -Recurse -Force }
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
    if (Test-Path -LiteralPath $release) { Remove-Item -LiteralPath $release -Force }
}

Write-Host "Artifact TOCTOU reparse safety check passed."
