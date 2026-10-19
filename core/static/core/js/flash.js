import { alerta, aviso, Swal } from "./alerts.js";

window.sgrFlashReady = true;

const STORAGE_KEY = "sgr-notice";
const NOTICE_LIFETIME = 10000;

const ICONS = { success: "success", error: "error", warning: "warning", info: "info" };

export function showOnNextPage(notice) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...notice, at: Date.now() }));
  } catch {
  }
}

function takeStored() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(STORAGE_KEY);
    const notice = JSON.parse(raw);
    return notice && Date.now() - Number(notice.at) < NOTICE_LIFETIME ? notice : null;
  } catch {
    return null;
  }
}

function takeInline() {
  const found = [];
  document.querySelectorAll(".flash [data-flash]").forEach((box) => {
    const text = (box.querySelector("[data-flash-text]") || box).textContent.trim();
    if (text) found.push({ level: box.dataset.flash, tags: (box.dataset.flashTags || "").split(/\s+/), text });
  });
  document.querySelectorAll(".flash").forEach((flash) => flash.remove());
  return found;
}

function show({ level, tags, text }) {
  if (level === "info" || tags.includes("toast")) {
    return aviso.fire({ icon: ICONS[level] || "info", title: text });
  }
  if (level === "success") {
    return alerta.fire({ icon: "success", title: "¡Listo!", text, timer: 4000, timerProgressBar: true });
  }
  if (level === "error") {
    return alerta.fire({ icon: "error", title: "No se pudo completar", text });
  }
  return alerta.fire({ icon: "warning", title: "Ten en cuenta", text });
}

async function whenFree() {
  while (Swal.isVisible()) {
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
}

async function run() {
  const notices = takeInline();
  const stored = takeStored();
  await whenFree();
  for (const notice of notices) {
    await show(notice);
    await whenFree();
  }
  if (stored) {
    await aviso.fire({ icon: "info", title: stored.title, text: stored.text });
  }
}

run();
