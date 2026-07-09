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
if ffmpeg_path:
    # Падаем громко, если FFMPEG_PATH задан, но файла нет: раньше это молча
    # пропускало бандлинг ffmpeg (см. windows-latest баг с POSIX-путём из
    # bash), и релиз без ffmpeg расходился пользователям без предупреждения.
    if not os.path.exists(ffmpeg_path):
        raise FileNotFoundError(f"FFMPEG_PATH={ffmpeg_path!r} does not exist, ffmpeg would be missing from the build")
    # На Windows choco кладёт в PATH редиректор-шим вместо настоящего бинарника
    # (несколько КБ, хардкодит абсолютный путь на CI-машине) - он не работает в
    # отрыве от машины, где был установлен, и в собранном приложении выглядит
    # как "ffmpeg not installed", хотя файл вроде бы на месте. Реальная сборка
    # ffmpeg весит десятки-сотни МБ. Проверяем только на Windows - это местная
    # особенность choco, brew на macOS шимов не делает.
    if sys.platform == "win32":
        MIN_FFMPEG_SIZE = 1_000_000
        if os.path.getsize(ffmpeg_path) < MIN_FFMPEG_SIZE:
            raise FileNotFoundError(
                f"FFMPEG_PATH={ffmpeg_path!r} is only {os.path.getsize(ffmpeg_path)} bytes - "
                "looks like a shim/redirector, not the real ffmpeg binary"
            )
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
