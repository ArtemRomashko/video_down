# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_DIR = os.path.dirname(SPEC_DIR)

datas = [(os.path.join(SPEC_DIR, "ui"), "ui")]
binaries = []
hiddenimports = []

for pkg in ("yt_dlp", "curl_cffi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

ffmpeg_path = os.environ.get("FFMPEG_PATH")
if ffmpeg_path and os.path.exists(ffmpeg_path):
    binaries.append((ffmpeg_path, "."))
    # ffprobe нужен для проверки кодека после скачивания (см. downloader.py) -
    # он всегда лежит рядом с ffmpeg в той же папке дистрибутива.
    probe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), probe_name)
    if os.path.exists(ffprobe_path):
        binaries.append((ffprobe_path, "."))

icon_ico = os.path.join(SPEC_DIR, "assets", "icon.ico")
icon_icns = os.path.join(SPEC_DIR, "assets", "icon.icns")

a = Analysis(
    [os.path.join(SPEC_DIR, "app.py")],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VideoBust",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get("VIDEOBUST_DEBUG_CONSOLE") == "1",
    disable_windowed_traceback=False,
    icon=icon_ico if os.path.exists(icon_ico) else None,
)

if sys.platform == "darwin":
    # Падаем громко, если .icns не собрался, вместо тихого отката на дефолтную
    # иконку PyInstaller: молчаливый os.path.exists()-фоллбэк уже один раз
    # незаметно "съел" нашу иконку в mac-сборке.
    if not os.path.exists(icon_icns):
        raise FileNotFoundError(f"icon.icns not found at {icon_icns}, mac build icon step must have failed")
    app = BUNDLE(
        exe,
        name="VideoBust.app",
        bundle_identifier="com.videobust.app",
        info_plist={"NSHighResolutionCapable": True},
        icon=icon_icns,
    )
