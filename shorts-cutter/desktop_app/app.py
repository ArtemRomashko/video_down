#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Десктоп-приложение (Windows/macOS) поверх downloader.py: то же скачивание
YouTube/Instagram/TikTok/Facebook/Pinterest, но с окном вместо консоли.
"""

import datetime
import json
import os
import subprocess
import sys
import threading

import webview

from version import __version__ as APP_VERSION

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)

# В dev-режиме downloader.py лежит на уровень выше (shorts-cutter/).
# В собранном .exe/.app он уже встроен PyInstaller-ом как обычный модуль.
if not FROZEN:
    sys.path.insert(0, os.path.dirname(APP_DIR))

from downloader import DownloadCancelled, DownloadError, download_video as run_download  # noqa: E402
import notifications  # noqa: E402
import updater  # noqa: E402

UI_DIR = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "ui")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".videobust", "config.json")

# Собранное приложение может лежать в доступной только для чтения папке
# (Program Files, /Applications), поэтому по умолчанию пишем в домашнюю папку пользователя.
# Пользователь может сменить папку в интерфейсе — выбор запоминается в CONFIG_PATH.
if FROZEN:
    DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "VideoBust downloads")
    FFMPEG_LOCATION = os.path.join(sys._MEIPASS, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
else:
    DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(APP_DIR), "output")
    FFMPEG_LOCATION = None


def _load_output_dir():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f).get("output_dir")
    except (OSError, ValueError):
        saved = None
    return saved if saved and os.path.isdir(saved) else DEFAULT_OUTPUT_DIR


def _save_output_dir(path):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"output_dir": path}, f)


# Ссылка на окно хранится отдельно от Api, а не как self.window: если Api держит
# атрибут-ссылку на Window (а Window держит ссылку на Api через js_api), pywebview's
# .NET-мост при обходе accessibility-дерева окна зацикливается на этом цикле ссылок
# и падает в RecursionError. Модуль-level переменная в этот обход не попадает.
_window = None
_output_dir = _load_output_dir()
_last_update_info = None
_cancel_event = threading.Event()


class Api:
    def _push_progress(self, data):
        if _window is None:
            return
        _window.evaluate_js(f"window.onProgress({json.dumps(data)})")

    def get_output_dir(self):
        return _output_dir

    def choose_output_folder(self):
        global _output_dir
        result = _window.create_file_dialog(webview.FileDialog.FOLDER, directory=_output_dir)
        if not result:
            return None
        _output_dir = result[0]
        _save_output_dir(_output_dir)
        return _output_dir

    def download_video(self, url):
        _cancel_event.clear()
        try:
            path = run_download(
                url,
                progress_callback=self._push_progress,
                output_dir=_output_dir,
                ffmpeg_location=FFMPEG_LOCATION,
                cancel_event=_cancel_event,
            )
        except DownloadCancelled:
            return {"ok": False, "cancelled": True}
        except DownloadError as e:
            return self._error_response(url, e)
        except Exception as e:
            return self._error_response(url, e)
        notifications.notify("Video Bust: готово", os.path.basename(path))
        return {"ok": True, "path": path, "filename": os.path.basename(path)}

    def cancel_download(self):
        _cancel_event.set()

    @staticmethod
    def _error_response(url, exc):
        # Полный диагностический блок, который пользователь может просто скопировать
        # и прислать целиком - вместо пересказа своими словами, что пошло не так.
        diagnostic = (
            f"Video Bust v{APP_VERSION} ({sys.platform})\n"
            f"Ссылка: {url}\n"
            f"Тип ошибки: {type(exc).__name__}\n"
            f"Сообщение: {exc}\n"
            f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        notifications.notify("Video Bust: не получилось скачать", str(exc))
        return {"ok": False, "error": str(exc), "diagnostic": diagnostic}

    def open_output_folder(self):
        os.makedirs(_output_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(_output_dir)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", _output_dir], check=False)
        else:
            subprocess.run(["xdg-open", _output_dir], check=False)

    def check_for_update(self):
        # sys.executable в dev-режиме - это python.exe, его подменять нельзя.
        global _last_update_info
        if not FROZEN:
            return None
        _last_update_info = updater.check_for_update()
        return _last_update_info

    def _push_update_progress(self, data):
        if _window is None:
            return
        _window.evaluate_js(f"window.onUpdateProgress({json.dumps(data)})")

    def apply_update(self):
        if not FROZEN or _last_update_info is None:
            return {"ok": False, "error": "Обновление недоступно"}
        try:
            updater.apply_update(_last_update_info["url"], progress_callback=self._push_update_progress)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        # Хелпер-скрипт уже запущен и ждёт, пока мы выйдем, чтобы подменить файл и перезапустить
        # (см. updater.py про PYINSTALLER_RESET_ENVIRONMENT - без него перезапущенный
        # exe падал с "Failed to load Python DLL").
        threading.Timer(0.5, lambda: _window.destroy()).start()
        return {"ok": True}


def main():
    global _window
    api = Api()
    _window = webview.create_window(
        "Video Bust",
        os.path.join(UI_DIR, "index.html"),
        js_api=api,
        width=620,
        height=620,
        resizable=True,
        background_color="#0e0f13",
    )
    webview.start()


if __name__ == "__main__":
    main()
