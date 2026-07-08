#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
СКАЧИВАНИЕ ВИДЕО В МАКСИМАЛЬНОМ КАЧЕСТВЕ
=========================================
Скачивает видео по ссылке (YouTube, Instagram, TikTok и всё, что понимает yt-dlp)
в максимальном доступном у источника разрешении и с лучшим звуком.

КАК ПОЛЬЗОВАТЬСЯ:
1. Установи зависимости один раз:
   pip install yt-dlp
   (ffmpeg должен быть установлен в системе: https://ffmpeg.org/download.html)

2. Запусти: python script.py <ссылка>
   или просто python script.py — скрипт спросит ссылку.

Готовый файл сохраняется в папку output/.
"""

import os
import shutil
import sys

if sys.platform == "win32":
    # Иначе кириллица в print() превращается в кракозябры в cmd/PowerShell с не-UTF8 кодовой страницей
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    os.system("chcp 65001 > NUL")

from downloader import OUTPUT_DIR, DownloadError, download_video


def check_dependencies():
    """Проверяет, что ffmpeg вообще есть в PATH, до начала работы."""
    if shutil.which("ffmpeg") is None:
        print("Не найден в PATH: ffmpeg.")
        print("Установи ffmpeg: https://ffmpeg.org/download.html")
        sys.exit(1)


def main():
    check_dependencies()

    url = sys.argv[1] if len(sys.argv) > 1 else input("Ссылка на видео (YouTube/Instagram/TikTok): ").strip()
    if not url:
        print("Ссылка не указана.")
        sys.exit(1)

    print(f"Скачиваю: {url}")
    try:
        download_video(url)
    except DownloadError:
        print("\nНе получилось скачать видео через yt-dlp.")
        print("Проверь: ссылка правильная, видео не приватное/не удалено, есть интернет.")
        sys.exit(1)

    print(f"\nГотово! Файл сохранён в папке {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
