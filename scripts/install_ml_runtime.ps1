param(
    [string]$RequirementsFile = "requirements-ml.txt",
    [switch]$SkipFfmpeg
)

$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$requirementsPath = Join-Path $root $RequirementsFile

function Test-FfmpegAvailable {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Refresh-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Add-UserPathEntry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Entry
    )

    if (-not (Test-Path -LiteralPath $Entry)) {
        return $false
    }

    $normalizedEntry = [System.IO.Path]::GetFullPath($Entry).TrimEnd('\\')
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($userPath) {
        $parts = $userPath -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }

    $alreadyPresent = $parts | Where-Object { $_.TrimEnd('\\').ToLowerInvariant() -eq $normalizedEntry.ToLowerInvariant() }
    if (-not $alreadyPresent) {
        $newPath = if ($userPath) {
            ($userPath.TrimEnd(';') + ";" + $normalizedEntry)
        } else {
            $normalizedEntry
        }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }

    Refresh-SessionPath
    return $true
}

function Install-FfmpegWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    Write-Host "Trying FFmpeg install via winget..." -ForegroundColor Cyan
    & $winget.Source install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget install did not complete successfully (exit code: $LASTEXITCODE)." -ForegroundColor Yellow
        return $false
    }

    Refresh-SessionPath
    return (Test-FfmpegAvailable)
}

function Install-FfmpegPortable {
    $installRoot = Join-Path $env:LOCALAPPDATA "EMtranscriber\\ffmpeg"
    $installBin = Join-Path $installRoot "bin"
    $localFfmpeg = Join-Path $installBin "ffmpeg.exe"

    if (Test-Path -LiteralPath $localFfmpeg) {
        Add-UserPathEntry -Entry $installBin | Out-Null
        return (Test-FfmpegAvailable)
    }

    $downloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("emtranscriber_ffmpeg_" + [Guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempRoot "ffmpeg.zip"
    $extractPath = Join-Path $tempRoot "extract"

    New-Item -ItemType Directory -Path $extractPath -Force | Out-Null

    try {
        Write-Host "Trying FFmpeg portable install (download)..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        $ffmpegExe = Get-ChildItem -Path $extractPath -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
        if (-not $ffmpegExe) {
            throw "ffmpeg.exe not found in downloaded archive."
        }

        $sourceBin = Split-Path -Parent $ffmpegExe.FullName
        New-Item -ItemType Directory -Path $installBin -Force | Out-Null
        Copy-Item -Path (Join-Path $sourceBin "*") -Destination $installBin -Force

        Add-UserPathEntry -Entry $installBin | Out-Null
        return (Test-FfmpegAvailable)
    } catch {
        Write-Host ("Portable FFmpeg install failed: " + $_.Exception.Message) -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, "-m", "pip") }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source, "-m", "pip") }

    return $null
}

$pythonCmd = Resolve-PythonCommand
if (-not $pythonCmd) {
    Write-Host "Python launcher not found. Install Python 3.10+ and rerun this script." -ForegroundColor Red
    Write-Host "Press any key to close..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

if (-not (Test-Path $requirementsPath)) {
    Write-Host "requirements-ml.txt not found at: $requirementsPath" -ForegroundColor Red
    Write-Host "Press any key to close..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "Installing ML runtime requirements from: $requirementsPath" -ForegroundColor Cyan
& $pythonCmd[0] $pythonCmd[1] $pythonCmd[2] install --user -r $requirementsPath
$pipExitCode = $LASTEXITCODE
$overallExitCode = $pipExitCode

if ($pipExitCode -eq 0) {
    Write-Host "ML runtime dependencies installed successfully." -ForegroundColor Green
} else {
    Write-Host "Installation finished with errors (exit code: $pipExitCode)." -ForegroundColor Yellow
}

$ffmpegReady = $false
if ($SkipFfmpeg) {
    Write-Host "Skipping FFmpeg installation (SkipFfmpeg enabled)." -ForegroundColor Yellow
    $ffmpegReady = Test-FfmpegAvailable
} else {
    if (Test-FfmpegAvailable) {
        Write-Host "FFmpeg already available in PATH." -ForegroundColor Green
        $ffmpegReady = $true
    } else {
        $ffmpegReady = Install-FfmpegWithWinget
        if (-not $ffmpegReady) {
            $ffmpegReady = Install-FfmpegPortable
        }
    }
}

if ($ffmpegReady) {
    Write-Host "FFmpeg is available." -ForegroundColor Green
} else {
    Write-Host "FFmpeg installation not completed. Install it manually and ensure ffmpeg.exe is in PATH." -ForegroundColor Yellow
    if ($overallExitCode -eq 0) {
        $overallExitCode = 2
    }
}

if ($overallExitCode -eq 0) {
    Write-Host "Runtime setup completed successfully." -ForegroundColor Green
    Write-Host "If diarization still fails, ensure Hugging Face token is configured in app Settings."
} else {
    Write-Host "Runtime setup completed with warnings/errors (exit code: $overallExitCode)." -ForegroundColor Yellow
}

Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
exit $overallExitCode
