#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка и установка обновлений через GitHub Releases репозитория video_down.
Работает только в собранном приложении (FROZEN) — в dev-режиме sys.executable
указывает на python.exe, подменять его нельзя.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from version import __version__ as CURRENT_VERSION

REPO = "ArtemRomashko/video_down"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _current_build_number():
    try:
        return int(CURRENT_VERSION.rsplit(".", 1)[-1])
    except ValueError:
        return 0


def check_for_update():
    """Возвращает {"version": tag, "url": asset_url} если есть более новая версия, иначе None.
    Никогда не бросает исключения — при любой сетевой проблеме просто считаем, что обновлений нет.
    """
    try:
        req = urllib.request.Request(LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except Exception:
        return None

    tag = data.get("tag_name", "")
    try:
        latest_number = int(tag.lstrip("v").rsplit(".", 1)[-1])
    except (ValueError, IndexError):
        return None

    if latest_number <= _current_build_number():
        return None

    asset_suffix = "-windows.exe" if sys.platform == "win32" else "-macos.zip"
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(asset_suffix):
            return {"version": tag, "url": asset["browser_download_url"]}
    return None


def _download(url, progress_callback=None):
    tmp_dir = tempfile.mkdtemp(prefix="videobust_update_")
    dest = os.path.join(tmp_dir, url.rsplit("/", 1)[-1])

    def _hook(block_num, block_size, total_size):
        if progress_callback and total_size > 0:
            downloaded = min(block_num * block_size, total_size)
            progress_callback({"downloaded": downloaded, "total": total_size})

    urllib.request.urlretrieve(url, dest, reporthook=_hook)
    return dest


def _apply_windows(downloaded_exe):
    current_exe = sys.executable
    exe_name = os.path.basename(current_exe)
    script_path = os.path.join(tempfile.gettempdir(), "videobust_apply_update.bat")
    # PyInstaller onefile - это два процесса (внешний бутлоадер + внутренний, который
    # реально работает): ждать выхода только "нашего" PID недостаточно, второй процесс
    # с тем же именем может ещё держать файл несколько секунд после того, как окно
    # закрылось. Ждём, пока ЛЮБой процесс с этим именем образа полностью исчезнет,
    # и только потом подменяем файл и стартуем новую версию.
    # goto изнутри блока if (...) - известная ловушка cmd.exe, ломающая парсинг и
    # приводящая к зависанию батника. Поэтому все переходы - плоские, без вложенных скобок.
    script = (
        "@echo off\r\n"
        ":waitproc\r\n"
        f'tasklist /fi "imagename eq {exe_name}" 2>NUL | find /i "{exe_name}" >NUL\r\n'
        "if errorlevel 1 goto afterwaitproc\r\n"
        "timeout /t 1 /nobreak > NUL\r\n"
        "goto waitproc\r\n"
        ":afterwaitproc\r\n"
        ":wait\r\n"
        "timeout /t 1 /nobreak > NUL\r\n"
        f'move /y "{downloaded_exe}" "{current_exe}" > NUL 2>&1\r\n'
        "if errorlevel 1 goto wait\r\n"
        f'start "" "{current_exe}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    # PyInstaller onefile помечает свои дочерние процессы внутренними _PYI_*
    # переменными окружения, а "новый инстанс это тот же процесс" определяет по
    # СОВПАДЕНИЮ ПУТИ к exe (_PYI_ARCHIVE_FILE) - а у нас новый exe лежит ровно по
    # тому же пути (мы подменяем файл на месте). Поэтому новый процесс ошибочно решал,
    # что он - воркер той же самой (уже закрывающейся) родительской копии, и пытался
    # переиспользовать её временную папку распаковки, которая к тому моменту уже
    # удалена - отсюда "Failed to load Python DLL ...\_MEI########\python312.dll".
    # PYINSTALLER_RESET_ENVIRONMENT=1 - официальный флаг PyInstaller для этого случая
    # (restart приложения): заставляет бутлоадер считать процесс полностью новым.
    # https://pyinstaller.org/en/stable/advanced-topics.html
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    # ВАЖНО: не DETACHED_PROCESS - у такого процесса нет консоли вообще, а конвейер
    # "tasklist | find" внутри .bat на полностью безконсольном процессе зависает
    # намертво. CREATE_NO_WINDOW даёт процессу настоящую, но скрытую консоль - конвейеры
    # работают нормально. CREATE_BREAKAWAY_FROM_JOB - чтобы скрипт не погиб вместе с
    # закрывающимся родителем, если PyInstaller-бутлоадер держит его в своём Job Object.
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
    try:
        subprocess.Popen(["cmd", "/c", script_path], creationflags=flags, env=env, close_fds=True)
    except OSError:
        # Job не разрешает breakaway - запускаем как есть, это была наша лучшая попытка.
        subprocess.Popen(
            ["cmd", "/c", script_path],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            env=env,
            close_fds=True,
        )


def _apply_macos(downloaded_zip):
    # sys.executable -> VideoBust.app/Contents/MacOS/VideoBust
    app_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", "..", ".."))
    extract_dir = tempfile.mkdtemp(prefix="videobust_update_")
    shutil.unpack_archive(downloaded_zip, extract_dir)
    new_app = os.path.join(extract_dir, "VideoBust.app")

    pid = os.getpid()
    script_path = os.path.join(tempfile.gettempdir(), "videobust_apply_update.sh")
    script = (
        "#!/bin/bash\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.3; done\n"
        f'rm -rf "{app_path}"\n'
        f'mv "{new_app}" "{app_path}"\n'
        f'open "{app_path}"\n'
        'rm -- "$0"\n'
    )
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(script_path, 0o755)
    subprocess.Popen(["/bin/bash", script_path], start_new_session=True)


def apply_update(url, progress_callback=None):
    """Скачивает обновление и запускает хелпер-скрипт подмены. Сам процесс после
    этого должен закрыть окно (что приводит к штатному выходу) — хелпер ждёт его
    завершения и перезапускает приложение с новой версией.
    """
    downloaded = _download(url, progress_callback)
    if sys.platform == "win32":
        _apply_windows(downloaded)
    elif sys.platform == "darwin":
        _apply_macos(downloaded)
    else:
        raise RuntimeError(f"Автообновление не поддерживается на {sys.platform}")
