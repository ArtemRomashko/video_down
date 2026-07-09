# Video Bust

Десктоп-приложение (Windows + macOS) для скачивания видео максимального качества
(YouTube/Instagram/TikTok/Facebook/Pinterest/всё, что понимает yt-dlp). Один и тот же
код собирается в `.exe` (Windows) и `.app` (macOS) через PyInstaller в GitHub Actions.

Репозиторий: https://github.com/ArtemRomashko/video_down (origin/main).
`gh` CLI в этом окружении не установлен — GitHub опрашивать через `curl` напрямую
к `api.github.com` (см. раздел про CI ниже).

## Карта файлов

```
shorts-cutter/
  downloader.py          # общая логика скачивания (yt-dlp), используется и CLI, и десктопом
  script.py               # CLI-обёртка над downloader.py
  desktop_app/
    app.py                 # pywebview GUI, точка входа десктопа
    updater.py              # автообновление через GitHub Releases (общий код + Windows/macOS ветки)
    version.py               # версия сборки — ПЕРЕЗАПИСЫВАЕТСЯ в CI, в dev-режиме не трогать руками
    build.spec                # PyInstaller-спека, тут же логика бандлинга ffmpeg
    ui/                        # index.html / app.js / style.css — фронтенд, общий для обеих платформ
    assets/                     # icon.ico (Windows), icon.png -> icon.icns генерится в CI (macOS)
.github/workflows/build-desktop.yml  # сборка + релиз на каждый push в main
```

## Как читать присланную пользователем ошибку

Кнопка "Скопировать ошибку" в приложении (добавлена в 35c42df) отдаёт текст вида:

```
Video Bust v1.0.14 (win32)
Ссылка: https://...
Тип ошибки: DownloadError
Сообщение: ...
Время: 2026-07-09 18:22:19
```

- `v1.0.14` — это `1.0.<github_run_number>`, задаётся в CI шагом "Write version"
  (см. build-desktop.yml). Тег релиза с этим же номером — `v1.0.14`. По номеру
  можно найти точный коммит: `git log --oneline` + сопоставить с временем публикации
  релиза, либо через API (ниже).
- `(win32)` / `(darwin)` — платформа, сразу отсекает половину кода при разборе.
- `Тип ошибки` — как правило `DownloadError` (см. `downloader.py: DownloadError`)
  или голое исключение Python, если поймано в `except Exception` в `app.py`.

Первым делом проверить, актуальна ли версия у пользователя (есть ли более новый
релиз с фиксом), и когда была собрана его версия относительно последних пушей в main.

## Windows-специфика

- Автообновление (`updater.py: _apply_windows`) — двухпроцессный PyInstaller onefile:
  батник ждёт, пока ЛЮБОЙ процесс с именем exe исчезнет из `tasklist`, потом
  `move` + перезапуск с `PYINSTALLER_RESET_ENVIRONMENT=1` (без этого новый процесс
  ошибочно считает себя воркером старого и пытается переиспользовать уже удалённую
  temp-папку распаковки — падает с "Failed to load Python DLL").
- ffmpeg собирается через `choco install ffmpeg -y` в CI. **Ловушка**: `choco`
  кладёт в `chocolatey\bin` не сам бинарник, а крошечный shim-редиректор (десятки КБ),
  который хардкодит абсолютный путь к реальному ffmpeg в `chocolatey\lib` НА
  CI-МАШИНЕ. Если бандлить этот shim (например, если находить ffmpeg через
  `Get-Command`/`where`/`command -v`) — на компьютере пользователя он не находит
  свою цель и падает, что выглядит как "ffmpeg not installed", хотя файл вроде бы
  есть. Правильно — искать настоящий `ffmpeg.exe` рекурсивно под
  `$env:ChocolateyInstall\lib`, а не резолвить через PATH. См. шаг
  "Locate ffmpeg (Windows)" в build-desktop.yml и историю коммитов
  `67026b7` → `0ddbabd` (тот самый баг, ловился дважды подряд).
- `build.spec` дополнительно проверяет размер файла (`< 1MB` = подозрение на shim)
  — но **только на Windows** (`sys.platform == "win32"`), потому что на macOS этот
  же чек однажды сломал сборку (`e19a8d7` откатывал его на macOS после того, как
  он ошибочно применился и там).
- SSL в `updater.py` берёт CA-бандл из `certifi` явно — на Windows это не
  критично (тянет сертификаты из системного хранилища), но код общий для
  обеих платформ, менять только если реально нужно.

## macOS-специфика

- Автообновление (`updater.py: _apply_macos`) — три исторических бага, все
  почищены в `5d9e422`, держать в уме при новых правках этого куска:
  1. SSL без `certifi` → `CERTIFICATE_VERIFY_FAILED` (в бандле нет системного
     хранилища сертификатов).
  2. `app_path` считался с тремя `..` вместо двух → указывал на папку РЯДОМ
     с `.app`, и helper делал `rm -rf` по ней — снёс бы всё соседнее у
     пользователя. Правильно — два уровня вверх (`MacOS -> Contents -> .app`).
  3. `shutil.unpack_archive`/`zipfile` теряет unix-бит исполняемости → после
     распаковки `open` падает с "Launchd job spawn failed". Распаковывать
     только через `ditto` (им же архив и собирается в CI, см. workflow).
- `open` после подмены бандла оборачивается в retry-цикл — LaunchServices
  иногда ещё держит старую регистрацию бандла по этому пути.
- ffmpeg — `brew install ffmpeg`, реальный бинарник, никаких shim-ловушек
  (в отличие от Windows/choco). Отдельная size-проверка в build.spec ей не
  нужна и не применяется.
- `.icns` иконка генерится в CI из `assets/icon.png` (`sips` + `iconutil`).
  `build.spec` падает громко, если `.icns` не собрался — не превращать это
  обратно в тихий fallback.

## CI/CD (build-desktop.yml)

- Триггер: push в `main`, затрагивающий `shorts-cutter/**` или сам workflow-файл.
- Версия = `1.0.<github.run_number>`, релиз = тег `v1.0.<run_number>`, публикуется
  автоматически job'ом `release` (softprops/action-gh-release).
- Матрица `windows-latest` + `macos-latest` — это ОДИН job `build` с двумя
  прогонами. **Если упала хотя бы одна платформа — `release` пропускается целиком**,
  даже если вторая платформа собралась и было бы что публиковать. Проверять статус
  ОБЕИХ платформ, а не только той, что чинили.
- Проверка статуса без `gh`:
  ```
  curl -s "https://api.github.com/repos/ArtemRomashko/video_down/actions/runs?per_page=5"
  curl -s "https://api.github.com/repos/ArtemRomashko/video_down/releases?per_page=5"
  curl -s "https://api.github.com/repos/ArtemRomashko/video_down/commits/main/check-runs"
  ```
  Всё это анонимно работает на публичном репо. А вот
  `.../actions/jobs/{id}/logs` требует токен даже на публичном репо (403 "Must
  have admin rights") — подробный текст ошибки из упавшего шага так просто не
  достать, только `check-runs/{id}/annotations` (часто там лишь
  "Process completed with exit code 1", без деталей) и общая логика/диффы.

## Когда прилетел новый пуш от другой сессии/платформы — процедура переноса фич

Периодически в `main` прилетают коммиты, сделанные "по мотивам" работы на одной
платформе (например фикс автообновления только для macOS). Перед тем как чинить
что-то на своей платформе, и после того как почистил — проверять:

1. `git fetch && git log --oneline main..origin/main` — что нового.
2. `git show --stat <sha>` на каждый новый коммит — какие файлы тронуты.
3. Разделить изменения на:
   - **Общий код** (downloader.py, UI-тексты, docstring'и, общие функции в
     updater.py типа `_ssl_context`/`check_for_update`/`_download`) — уже
     работает на обеих платформах одинаково, переносить не нужно, просто не
     сломать при ребейзе.
   - **Платформенно-специфичный фикс** (`_apply_windows` vs `_apply_macos`,
     ветки `sys.platform ==`, отдельные шаги в build.spec/workflow) — НЕ
     копировать бездумно на другую платформу. Сначала проверить, воспроизводится
     ли та же первопричина там (например: SSL-фикс был нужен, потому что
     PyInstaller-бандл без системного хранилища сертификатов — на Windows
     ssl тянет из системного хранилища, тот же баг там не воспроизводится,
     переносить нечего). Если первопричина действительно общая — чинить
     аналогично, но отдельным явным изменением для своей платформы, не трогая
     код другой.
4. Если правишь `build.spec` — помнить, что это ОДИН файл на обе платформы:
   любой новый чек должен быть либо действительно платформонезависимым, либо
   явно обёрнут в `if sys.platform == "win32"` / `"darwin"` (см. историю с
   size-check ffmpeg, которая один раз сломала macOS-сборку, потому что чек
   не был так обёрнут).
5. Rebase, а не merge, при расхождении с origin/main (`git rebase origin/main`
   перед пушем) — история в этом репо держится линейной.
