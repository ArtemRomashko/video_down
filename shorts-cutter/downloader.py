#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Общая логика скачивания видео (YouTube/Instagram/TikTok/Facebook/Pinterest/всё, что понимает yt-dlp)
в максимальном качестве. Используется и CLI-скриптом (script.py), и десктоп-приложением.
"""

import os
import re
import subprocess
import sys

import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Кодеки, которые QuickTime (и многие Windows-плееры/монтажки) не понимают вообще.
# HEVC сюда не входит - Apple поддерживает его нативно с 2017 года.
INCOMPATIBLE_VIDEO_CODECS = {"av1", "vp9"}

_SUBPROCESS_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


class DownloadError(Exception):
    pass


# Символы, запрещённые в именах файлов на Windows (и не желательные на macOS).
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(name):
    """Готовит пользовательское название к использованию как имя файла:
    вырезает запрещённые на Windows символы и хвостовые точки/пробелы
    (Windows их молча отбрасывает, из-за чего файл может не найтись по
    ожидаемому имени)."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "video"


# yt_dlp.utils.DownloadCancelled - штатное исключение самого yt-dlp для прерывания
# скачивания (используется им же для --max-downloads и т.п.): пробрасывается через
# extract_info() как есть, не оборачивается в DownloadError. Раскачано наружу отсюда,
# чтобы вызывающему коду (CLI, desktop) не нужно было импортировать yt_dlp напрямую.
DownloadCancelled = yt_dlp.utils.DownloadCancelled


# Сайты News Corp Australia (news.com.au, dailytelegraph, heraldsun, couriermail,
# theaustralian и прочие мастхеды сети) прячут видео за собственным JS-плеером "AVP",
# который generic-экстрактор yt-dlp не распознаёт, а сам HTML при этом отдаётся
# только браузерным User-Agent'ам (иначе 403 Forbidden). Внутри страницы лежит
# ссылка на реальный Brightcove-плеер в виде assetId "{account_id}-{video_id}",
# например: "assetId":"5348771529001-6400316285112". Достаём его и собираем прямой
# Brightcove-URL, который yt-dlp уже умеет качать нативно.
_NEWSCORP_ASSET_RE = re.compile(r'"assetId"\s*:\s*"(\d+)-(\d+)"')
_BRIGHTCOVE_URL_TMPL = "https://players.brightcove.net/{account}/default_default/index.html?videoId={video}"
# Общий для сети постоянный формат пермалинка — /news-story/<hash> — плюс сам домен .com.au.
_NEWSCORP_HINTS = ("/news-story/", ".com.au")


def _resolve_newscorp_brightcove(url):
    """Если url ведёт на статью News Corp Australia с видео, возвращает прямой
    Brightcove-URL, который yt-dlp скачает нативно; иначе None. Страница тянется с
    браузерным отпечатком через curl_cffi (обычный UA получает 403). Ошибки сети/
    парсинга проглатываются - это фолбэк, а не основной путь."""
    if not any(hint in url for hint in _NEWSCORP_HINTS):
        return None
    try:
        from curl_cffi import requests as cffi_requests
        html = cffi_requests.get(url, impersonate="chrome", timeout=30).text
    except Exception:
        return None
    match = _NEWSCORP_ASSET_RE.search(html)
    if not match:
        return None
    return _BRIGHTCOVE_URL_TMPL.format(account=match.group(1), video=match.group(2))


def _ffprobe_path(ffmpeg_location):
    if ffmpeg_location:
        probe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        candidate = os.path.join(os.path.dirname(ffmpeg_location), probe_name)
        if os.path.exists(candidate):
            return candidate
    return "ffprobe"


def _video_codec(path, ffmpeg_location):
    try:
        result = subprocess.run(
            [
                _ffprobe_path(ffmpeg_location), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0", path,
            ],
            capture_output=True, text=True, timeout=15, **_SUBPROCESS_FLAGS,
        )
        return result.stdout.strip().lower()
    except Exception:
        return ""


def _ensure_compatible_codec(path, ffmpeg_location, progress_callback):
    """Если видео в AV1/VP9 (QuickTime и многие плееры их не открывают) - перекодирует
    в H.264 через ffmpeg. Не бросает исключений: если перекодирование не удалось,
    файл остаётся как есть - скачанное видео лучше, чем никакого.
    """
    if _video_codec(path, ffmpeg_location) not in INCOMPATIBLE_VIDEO_CODECS:
        return
    if progress_callback:
        progress_callback({"status": "transcoding"})
    ffmpeg = ffmpeg_location or "ffmpeg"
    tmp_path = path + ".h264.mp4"
    try:
        subprocess.run(
            [
                ffmpeg, "-y", "-i", path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                tmp_path,
            ],
            check=True, capture_output=True, **_SUBPROCESS_FLAGS,
        )
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _build_hook(progress_callback, cancel_event=None):
    def hook(d):
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled("Скачивание отменено пользователем")
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


def download_video(url, progress_callback=None, output_dir=None, ffmpeg_location=None, cancel_event=None, filename=None):
    """Скачивает видео по ссылке в output_dir (по умолчанию OUTPUT_DIR) и возвращает путь к итоговому файлу.

    progress_callback(dict) вызывается на каждый прогресс-евент yt-dlp, если передан.
    ffmpeg_location позволяет указать путь к конкретному ffmpeg вместо поиска в PATH
    (нужно для собранного desktop-приложения, где ffmpeg вшит рядом с exe).
    cancel_event (threading.Event) - если установлен на момент очередного прогресс-евента
    yt-dlp, скачивание прерывается с DownloadCancelled. Проверяется только во время самой
    закачки - на этапах извлечения метаданных, слияния и транскодирования отмена не
    подхватывается.
    filename - опциональное пользовательское имя файла (без расширения). Если не задано,
    имя берётся из title видео, как и раньше.
    """
    output_dir = output_dir or OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    name_part = _sanitize_filename(filename) if filename else "%(title)s"

    ydl_opts = {
        # Сначала пробуем H.264 (avc1) видео + AAC звук - это единственная комбинация,
        # которую гарантированно проигрывают QuickTime, стандартные плееры Windows и
        # монтажные программы. AV1/VP9 (их YouTube часто отдаёт как "лучшее" на высоких
        # разрешениях) QuickTime не воспроизводит вообще. Если у источника вообще нет
        # H.264-варианта - откатываемся на просто самое лучшее, что есть.
        "format": "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[vcodec^=avc1]/bv*+ba/b",
        # Сортируем по разрешению в первую очередь, mp4/m4a - только как tie-breaker:
        # жёсткий фильтр по контейнеру мог тихо срезать реальный максимум разрешения источника.
        "format_sort": ["res", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(output_dir, f"{name_part}.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [_build_hook(progress_callback, cancel_event)],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    def _extract(target_url):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=True)
            return ydl.prepare_filename(info)

    try:
        filename = _extract(url)
    except yt_dlp.utils.DownloadError as e:
        # Generic-экстрактор не осилил ссылку (403 или "Unsupported URL") - пробуем
        # распознать в ней спрятанное Brightcove-видео News Corp AU и качаем уже его.
        brightcove_url = _resolve_newscorp_brightcove(url)
        if brightcove_url is None:
            raise DownloadError(str(e)) from e
        try:
            filename = _extract(brightcove_url)
        except yt_dlp.utils.DownloadError as e2:
            raise DownloadError(str(e2)) from e2

    merged_path = os.path.splitext(filename)[0] + ".mp4"
    final_path = merged_path if os.path.exists(merged_path) else filename
    _ensure_compatible_codec(final_path, ffmpeg_location, progress_callback)
    return final_path
