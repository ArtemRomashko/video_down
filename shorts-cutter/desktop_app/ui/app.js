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
  }
};

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

if (window.pywebview) {
  initOutputDir();
} else {
  window.addEventListener("pywebviewready", initOutputDir);
}
