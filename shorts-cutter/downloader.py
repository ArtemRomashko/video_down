#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Общая логика скачивания видео (YouTube/Instagram/TikTok/всё, что понимает yt-dlp)
в максимальном качестве. Используется и CLI-скриптом (script.py), и десктоп-приложением.
"""

import os

import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


class DownloadError(Exception):
    pass


def _build_hook(progress_callback):
    def hook(d):
        if progress_callback is None:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            progress_callback({
                "status": "downloading",
                "downloaded_bytes": d.get("downloaded_bytes", 0),
                "total_bytes": total,
                "speed": d.get("speed"),
                "eta": d.get("eta"),
            })
        elif d["status"] == "finished":
            progress_callback({"status": "merging"})
    return hook


def download_video(url, progress_callback=None, output_dir=None, ffmpeg_location=None):
    """Скачивает видео по ссылке в output_dir (по умолчанию OUTPUT_DIR) и возвращает путь к итоговому файлу.

    progress_callback(dict) вызывается на каждый прогресс-евент yt-dlp, если передан.
    ffmpeg_location позволяет указать путь к конкретному ffmpeg вместо поиска в PATH
    (нужно для собранного desktop-приложения, где ffmpeg вшит рядом с exe).
    """
    output_dir = output_dir or OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bv*+ba/b",
        # Сортируем по разрешению в первую очередь, mp4/m4a - только как tie-breaker:
        # жёсткий фильтр по контейнеру мог тихо срезать реальный максимум разрешения источника.
        "format_sort": ["res", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [_build_hook(progress_callback)],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(str(e)) from e

    merged_path = os.path.splitext(filename)[0] + ".mp4"
    return merged_path if os.path.exists(merged_path) else filename
