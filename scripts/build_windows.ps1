param(
    [string]$Name = "EMtranscriber",
    [string]$Entry = "src\emtranscriber\main.py",
    [ValidateSet("ui-shell", "full-ml")]
    [string]$Profile = "ui-shell"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$iconPath = Join-Path $projectRoot "packaging\assets\emtranscriber.ico"

# Rebuild embedded UI resources and icon from images/ before packaging.
python (Join-Path $projectRoot "scripts\sync_branding_resources.py")
if ($LASTEXITCODE -ne 0) {
    throw "Branding resource sync failed with exit code $LASTEXITCODE"
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", $Name,
    "--windowed",
    "--onedir",
    "--paths", "src",
    "--add-data", "migrations;migrations",
    "--add-data", "LICENSE;.",
    "--add-data", "requirements-ml.txt;.",
    "--add-data", "scripts/install_ml_runtime.ps1;.",
    # Keep real pipeline modules packaged even in ui-shell profile.
    # Heavy ML libs are still excluded there and loaded from local Python site-packages at runtime.
    "--hidden-import", "emtranscriber.infrastructure.asr.faster_whisper_service",
    "--hidden-import", "emtranscriber.infrastructure.diarization.pyannote_service",
    # ctranslate2/torch and nested deps import several stdlib modules dynamically in frozen mode.
    "--hidden-import", "ctypes",
    "--hidden-import", "_ctypes",
    "--hidden-import", "ctypes.wintypes",
    "--hidden-import", "glob",
    "--hidden-import", "ipaddress",
    "--hidden-import", "configparser",
    "--hidden-import", "sysconfig",
    "--hidden-import", "http",
    "--hidden-import", "http.cookies",
    "--hidden-import", "xml",
    "--hidden-import", "xml.etree",
    "--hidden-import", "xml.etree.ElementTree",
    "--hidden-import", "xml.parsers",
    "--hidden-import", "xml.parsers.expat",
    "--hidden-import", "timeit",
    "--hidden-import", "importlib.resources",
    "--hidden-import", "importlib.metadata",
    "--hidden-import", "asyncio",
    "--hidden-import", "asyncio.base_events",
    "--hidden-import", "asyncio.coroutines",
    "--collect-submodules", "importlib",
    "--collect-submodules", "asyncio",
    "--collect-submodules", "http",
    "--collect-submodules", "xml"
)

if (Test-Path $iconPath) {
    $args += @("--icon", $iconPath)
} else {
    Write-Warning "Icon file not found after branding sync: $iconPath. Build will continue without custom icon."
}

if ($Profile -eq "ui-shell") {
    Write-Host "Building $Name with PyInstaller (UI shell profile)..."
    $args += @(
        "--exclude-module", "torch",
        "--exclude-module", "torchaudio",
        "--exclude-module", "torchcodec",
        "--exclude-module", "pytorch_lightning",
        "--exclude-module", "lightning",
        "--exclude-module", "pyannote",
        "--exclude-module", "pyannote.audio",
        "--exclude-module", "onnxruntime",
        "--exclude-module", "av"
    )
} else {
    Write-Host "Building $Name with PyInstaller (full-ml profile)..."
    $args += @(
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "pyannote.audio",
        "--collect-all", "pyannote.core",
        "--collect-all", "pyannote.pipeline"
    )
}

$args += $Entry

python @args

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

Write-Host "Build completed. Output: dist\\$Name"
