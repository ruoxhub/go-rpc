[CmdletBinding()]
param(
    [string]$OutputDirectory = "artifacts/sdk"
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$artifactsRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot "artifacts")).TrimEnd([IO.Path]::DirectorySeparatorChar)

if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    throw "OutputDirectory must be relative to artifacts/: $OutputDirectory"
}

try {
    $outputPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
} catch {
    throw "OutputDirectory is not a valid repository-relative path: $OutputDirectory"
}

$artifactsPrefix = $artifactsRoot + [IO.Path]::DirectorySeparatorChar
if ($outputPath -eq $artifactsRoot -or
    -not $outputPath.StartsWith($artifactsPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must be a child directory of artifacts/: $OutputDirectory"
}

function Test-ArtifactPathNoReparse {
    param(
        [string]$RootPath,
        [string]$TargetPath
    )

    $paths = New-Object System.Collections.Generic.List[string]
    $current = $TargetPath
    while ($true) {
        $paths.Add($current)
        if ($current -eq $RootPath) { break }
        $parent = Split-Path -Path $current -Parent
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $current) {
            throw "Unable to walk validated artifacts path: $TargetPath"
        }
        $current = $parent.TrimEnd([IO.Path]::DirectorySeparatorChar)
    }

    for ($index = $paths.Count - 1; $index -ge 0; $index--) {
        $path = $paths[$index]
        if (-not (Test-Path -LiteralPath $path)) { continue }
        Write-Verbose "Checking artifact path segment $path"
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "OutputDirectory crosses a reparse point: $path"
        }
    }
}

# Check every existing segment before creating the temp directory or touching output.
Test-ArtifactPathNoReparse $artifactsRoot $outputPath

if ($env:RPC_ARTIFACT_TEST_BEFORE_DELETE_MARKER) {
    [IO.File]::WriteAllText($env:RPC_ARTIFACT_TEST_BEFORE_DELETE_MARKER, "checked")
    $releaseDeadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $env:RPC_ARTIFACT_TEST_BEFORE_DELETE_RELEASE)) {
        if ([DateTime]::UtcNow -gt $releaseDeadline) {
            throw "artifact test release signal timed out"
        }
        Start-Sleep -Milliseconds 25
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("go-rpc-stage1-sdk-" + [Guid]::NewGuid().ToString("N"))
$javaProjectCache = Join-Path $tempRoot "java-project-cache"
$xposedProjectCache = Join-Path $tempRoot "xposed-project-cache"
$pythonOutput = Join-Path $tempRoot "python-dist"
$oldSourceDateEpoch = [Environment]::GetEnvironmentVariable("SOURCE_DATE_EPOCH", "Process")
$oldPythonNoBytecode = [Environment]::GetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "Process")
$oldGradleUserHome = [Environment]::GetEnvironmentVariable("GRADLE_USER_HOME", "Process")
$locationPushed = $false

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter()][string[]]$Arguments = @()
    )

    Write-Host "==> $Name"
    & $File @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}

function Get-SingleFile {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$Filter,
        [Parameter(Mandatory = $true)][string]$Kind
    )

    $files = @(Get-ChildItem -LiteralPath $Directory -File -Filter $Filter -ErrorAction Stop)
    if ($files.Count -ne 1) {
        throw "Expected exactly one $Kind in $Directory, found $($files.Count)"
    }
    return $files[0]
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $javaProjectCache -Force | Out-Null
    New-Item -ItemType Directory -Path $xposedProjectCache -Force | Out-Null
    New-Item -ItemType Directory -Path $pythonOutput -Force | Out-Null

    Push-Location -LiteralPath $repoRoot
    $locationPushed = $true

    # This is the exact validated target; no repository-wide cleanup is used.
    if (Test-Path -LiteralPath $outputPath) {
        Test-ArtifactPathNoReparse $artifactsRoot $outputPath
        Remove-Item -LiteralPath $outputPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

    $env:SOURCE_DATE_EPOCH = "1786636800"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    if ($null -eq $oldGradleUserHome) {
        $env:GRADLE_USER_HOME = Join-Path ([IO.Path]::GetTempPath()) "go-rpc-stage1-gradle-home"
    }

    $tsTgzDirectory = Join-Path $repoRoot "sdk/typescript/dist"
    $tsPackage = Get-Content -LiteralPath (Join-Path $repoRoot "sdk/typescript/package.json") -Raw | ConvertFrom-Json
    $tsPackageLeaf = ($tsPackage.name -replace "^@", "" -replace "/", "-") + "-" + $tsPackage.version + ".tgz"
    $oldTsPackage = Join-Path $tsTgzDirectory $tsPackageLeaf
    if (Test-Path -LiteralPath $oldTsPackage) { Remove-Item -LiteralPath $oldTsPackage -Force }
    Invoke-Checked "TypeScript SDK install" "npm.cmd" @("--prefix", "sdk/typescript", "ci")
    Invoke-Checked "TypeScript SDK test" "npm.cmd" @("--prefix", "sdk/typescript", "test")
    Invoke-Checked "TypeScript SDK pack" "npm.cmd" @("--prefix", "sdk/typescript", "run", "pack")
    $npmArtifact = Get-SingleFile $tsTgzDirectory "*.tgz" "npm package"

    Invoke-Checked "Python SDK editable install" "python" @("-m", "pip", "install", "-e", "sdk/python[dev]")
    Invoke-Checked "Python SDK tests" "python" @("-m", "unittest", "discover", "-s", "sdk/python/tests", "-v")
    Invoke-Checked "Python SDK build" "python" @("-m", "build", "sdk/python", "--outdir", $pythonOutput)
    $pythonWheel = Get-SingleFile $pythonOutput "*.whl" "Python wheel"
    $pythonSdist = Get-SingleFile $pythonOutput "*.tar.gz" "Python sdist"
    $normalizedSdist = Join-Path $tempRoot "normalized-sdist.tar.gz"
    $normalizeSdistCode = @'
import gzip
import os
import sys
import tarfile

source, destination = sys.argv[1:]
epoch = int(os.environ['SOURCE_DATE_EPOCH'])
with tarfile.open(source, 'r:gz') as source_tar, open(destination, 'wb') as destination_file:
    members = sorted(source_tar.getmembers(), key=lambda member: member.name)
    with gzip.GzipFile(fileobj=destination_file, mode='wb', filename='', mtime=epoch) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as destination_tar:
            for member in members:
                member.mtime = epoch
                member.uid = 0
                member.gid = 0
                member.uname = ''
                member.gname = ''
                member.pax_headers = {}
                content = source_tar.extractfile(member) if member.isfile() else None
                destination_tar.addfile(member, content)
                if content is not None:
                    content.close()
'@
    Invoke-Checked "Normalize Python sdist metadata" "python" @("-c", $normalizeSdistCode, $pythonSdist.FullName, $normalizedSdist)
    Move-Item -LiteralPath $normalizedSdist -Destination $pythonSdist.FullName -Force

    $gradlew = Join-Path $repoRoot "sample/xposed/gradlew.bat"
    Invoke-Checked "Java SDK test and jar" $gradlew @("-p", "sdk/java", "clean", "test", "jar", "--no-daemon", "--project-cache-dir", $javaProjectCache)
    $javaJar = Get-SingleFile (Join-Path $repoRoot "sdk/java/build/libs") "*.jar" "Java jar"
    Invoke-Checked "Xposed debug APK" $gradlew @("-p", "sample/xposed", ":app:clean", ":app:assembleDebug", "--no-daemon", "--project-cache-dir", $xposedProjectCache)
    $debugApk = Get-SingleFile (Join-Path $repoRoot "sample/xposed/app/build/outputs/apk/debug") "*.apk" "debug APK"

    $sources = @($npmArtifact, $pythonWheel, $pythonSdist, $javaJar, $debugApk)
    $sourceNames = @($sources | ForEach-Object { $_.Name })
    $uniqueNames = @($sourceNames | Sort-Object -Unique)
    if ($sourceNames.Count -ne 5 -or $uniqueNames.Count -ne 5) {
        throw "Artifact sources must contain five distinct leaf names"
    }
    foreach ($source in $sources) {
        Copy-Item -LiteralPath $source.FullName -Destination (Join-Path $outputPath $source.Name) -Force
    }

    $manifestNames = @($sources | ForEach-Object { $_.Name })
    [Array]::Sort($manifestNames, [StringComparer]::Ordinal)
    $manifestLines = foreach ($name in $manifestNames) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $outputPath $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $name"
    }
    $manifestPath = Join-Path $outputPath "SHA256SUMS"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($manifestPath, (($manifestLines -join "`n") + "`n"), $utf8NoBom)
    Write-Host "Artifacts written to $outputPath"
} finally {
    if ($locationPushed) { Pop-Location }
    if ($null -eq $oldSourceDateEpoch) { Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue } else { $env:SOURCE_DATE_EPOCH = $oldSourceDateEpoch }
    if ($null -eq $oldPythonNoBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue } else { $env:PYTHONDONTWRITEBYTECODE = $oldPythonNoBytecode }
    if ($null -eq $oldGradleUserHome) { Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue } else { $env:GRADLE_USER_HOME = $oldGradleUserHome }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
