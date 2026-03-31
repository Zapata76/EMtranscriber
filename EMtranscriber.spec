# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('migrations', 'migrations'), ('LICENSE', '.'), ('requirements-ml.txt', '.'), ('scripts/install_ml_runtime.ps1', '.')]
binaries = []
hiddenimports = ['emtranscriber.infrastructure.asr.faster_whisper_service', 'emtranscriber.infrastructure.diarization.pyannote_service', 'ctypes', '_ctypes', 'ctypes.util', 'ctypes.wintypes', 'glob', 'ipaddress', 'configparser', 'sysconfig', 'http', 'http.cookies', 'xml', 'xml.etree', 'xml.etree.ElementTree', 'xml.parsers', 'xml.parsers.expat', 'timeit', 'importlib.resources', 'importlib.metadata', 'asyncio', 'asyncio.base_events', 'asyncio.coroutines']
hiddenimports += collect_submodules('importlib')
hiddenimports += collect_submodules('asyncio')
hiddenimports += collect_submodules('http')
hiddenimports += collect_submodules('xml')
tmp_ret = collect_all('faster_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyannote.audio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyannote.core')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyannote.pipeline')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src\\emtranscriber\\main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torchcodec'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EMtranscriber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\workspace\\EMtranscriber\\packaging\\assets\\emtranscriber.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EMtranscriber',
)
