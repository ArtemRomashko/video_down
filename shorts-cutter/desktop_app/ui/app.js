const form = document.getElementById("download-form");
const urlInput = document.getElementById("url");
const downloadBtn = document.getElementById("download-btn");
const statusBlock = document.getElementById("status-block");
const statusText = document.getElementById("status-text");
const statusPercent = document.getElementById("status-percent");
const progressFill = document.getElementById("progress-fill");
const resultBlock = document.getElementById("result-block");
const resultIcon = document.getElementById("result-icon");
const resultTitle = document.getElementById("result-title");
const resultSubtitle = document.getElementById("result-subtitle");
const openFolderBtn = document.getElementById("open-folder-btn");
const openOutputLink = document.getElementById("open-output-link");
const outputDirEl = document.getElementById("output-dir");
const chooseFolderBtn = document.getElementById("choose-folder-btn");
const updateBanner = document.getElementById("update-banner");
const updateText = document.getElementById("update-text");
const updateBtn = document.getElementById("update-btn");

let downloading = false;

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

function setProgress(percent, indeterminate) {
  if (indeterminate) {
    progressFill.classList.add("indeterminate");
    progressFill.style.width = "";
  } else {
    progressFill.classList.remove("indeterminate");
    progressFill.style.width = `${percent}%`;
  }
}

function resetUi() {
  statusBlock.classList.remove("hidden");
  resultBlock.classList.add("hidden");
  setProgress(0, true);
  statusText.textContent = "Подготовка…";
  statusPercent.textContent = "";
}

function showResult(ok, title, subtitle, path) {
  statusBlock.classList.add("hidden");
  resultBlock.classList.remove("hidden");
  resultIcon.className = `result-icon ${ok ? "ok" : "err"}`;
  resultIcon.textContent = ok ? "✓" : "!";
  resultTitle.textContent = title;
  resultSubtitle.textContent = subtitle;
  openFolderBtn.classList.toggle("hidden", !ok);
  openFolderBtn.dataset.path = path || "";
}

// Вызывается из Python (window.pywebview.api -> evaluate_js) на каждый progress-хук yt-dlp.
window.onProgress = function onProgress(data) {
  if (data.status === "downloading") {
    if (data.total_bytes) {
      const percent = Math.min(100, (data.downloaded_bytes / data.total_bytes) * 100);
      setProgress(percent, false);
      statusPercent.textContent = `${percent.toFixed(0)}%`;
    } else {
      setProgress(0, true);
      statusPercent.textContent = formatBytes(data.downloaded_bytes);
    }
    statusText.textContent = "Скачиваю…";
  } else if (data.status === "merging") {
    setProgress(0, true);
    statusText.textContent = "Собираю видео и звук…";
    statusPercent.textContent = "";
  } else if (data.status === "transcoding") {
    setProgress(0, true);
    statusText.textContent = "Конвертирую для совместимости…";
    statusPercent.textContent = "";
  }
};

// Вызывается из Python во время скачивания обновления.
window.onUpdateProgress = function onUpdateProgress(data) {
  if (data.total) {
    const percent = Math.min(100, (data.downloaded / data.total) * 100);
    updateBtn.textContent = `Обновляю… ${percent.toFixed(0)}%`;
  } else {
    updateBtn.textContent = "Обновляю…";
  }
};

updateBtn.addEventListener("click", async () => {
  updateBtn.disabled = true;
  updateBtn.textContent = "Обновляю…";
  try {
    const result = await window.pywebview.api.apply_update();
    if (!result.ok) {
      updateBtn.disabled = false;
      updateBtn.textContent = "Обновить";
      updateText.textContent = `Не удалось обновить: ${result.error}`;
    }
    // При успехе приложение само перезапустится - тут ничего больше делать не нужно.
  } catch (err) {
    updateBtn.disabled = false;
    updateBtn.textContent = "Обновить";
    updateText.textContent = `Не удалось обновить: ${err}`;
  }
});

async function checkForUpdate() {
  try {
    const info = await window.pywebview.api.check_for_update();
    if (info) {
      updateText.textContent = `Доступна новая версия ${info.version}`;
      updateBanner.classList.remove("hidden");
    }
  } catch (err) {
    // тихо игнорируем - нет интернета/недоступен GitHub, не критично
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (downloading) return;

  const url = urlInput.value.trim();
  if (!url) return;

  downloading = true;
  downloadBtn.disabled = true;
  resetUi();

  try {
    const result = await window.pywebview.api.download_video(url);
    if (result.ok) {
      showResult(true, "Готово!", result.filename, result.path);
    } else {
      showResult(false, "Не получилось скачать", result.error);
    }
  } catch (err) {
    showResult(false, "Не получилось скачать", String(err));
  } finally {
    downloading = false;
    downloadBtn.disabled = false;
  }
});

openFolderBtn.addEventListener("click", () => {
  window.pywebview.api.open_output_folder();
});

openOutputLink.addEventListener("click", () => {
  window.pywebview.api.open_output_folder();
});

chooseFolderBtn.addEventListener("click", async () => {
  const newDir = await window.pywebview.api.choose_output_folder();
  if (newDir) {
    outputDirEl.textContent = newDir;
    outputDirEl.title = newDir;
  }
});

async function initOutputDir() {
  const dir = await window.pywebview.api.get_output_dir();
  outputDirEl.textContent = dir;
  outputDirEl.title = dir;
}

function initApp() {
  initOutputDir();
  checkForUpdate();
}

if (window.pywebview) {
  initApp();
} else {
  window.addEventListener("pywebviewready", initApp);
}
