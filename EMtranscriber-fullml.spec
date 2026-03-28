# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path(__file__).resolve().parent
icon_path = project_root / "packaging" / "assets" / "emtranscriber.ico"
sidebar_candidates = [
    project_root / "packaging" / "assets" / "main_sidebar_image.png",
    project_root / "packaging" / "assets" / "main_sidebar_image.jpg",
    project_root / "packaging" / "assets" / "main_sidebar_image.jpeg",
]

datas = [('migrations', 'migrations'), ('LICENSE', '.')]
if icon_path.exists():
    datas.append((str(icon_path), 'packaging/assets'))
for sidebar_path in sidebar_candidates:
    if sidebar_path.exists():
        datas.append((str(sidebar_path), 'packaging/assets'))
        break

binaries = []
hiddenimports = [
    'emtranscriber.infrastructure.asr.faster_whisper_service',
    'emtranscriber.infrastructure.diarization.pyannote_service',
    'ipaddress',
    'configparser', 'sysconfig',
    'http',
    'http.cookies',
    'xml',
    'xml.etree',
    'xml.etree.ElementTree',
    'xml.parsers',
    'xml.parsers.expat',
    'timeit',
]

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
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EMtranscriber-fullml',
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
    icon=str(icon_path) if icon_path.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EMtranscriber-fullml',
)



