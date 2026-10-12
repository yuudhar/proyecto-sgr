// Avisos de Django (el framework de mensajes) como ventanas de SweetAlert2.
//
// Quien dice qué pasó es el servidor: solo manda «éxito» cuando la operación se hizo, y manda «error» cuando no.
// Aquí solo se muestran:
//   éxito          ventana con el ícono verde que se cierra sola a los 4 segundos (o con «Entendido»)
//   error          ventana roja que espera a que la persona la cierre
//   advertencia    ventana amarilla que espera a que la persona la cierre
//   información    aviso corto en la esquina, que se cierra solo (también lo que traiga la etiqueta «toast»)
//
// Sin JavaScript, o si este script no llega a correr, los mismos avisos se ven como siempre arriba de la página
// (core/partials/flash.html): sgr.js los vuelve a mostrar si flash.js no avisó que está listo.

import { alerta, aviso, Swal } from "./alerts.js";

window.sgrFlashReady = true;

const STORAGE_KEY = "sgr-notice";
const NOTICE_LIFETIME = 10000; // un aviso guardado para la página siguiente vale solo unos segundos

const ICONS = { success: "success", error: "error", warning: "warning", info: "info" };

// Avisos pendientes para la página que sigue: por ejemplo «Registro cancelado» al volver de un formulario.
// El almacenamiento del navegador puede no estar disponible (ventana privada, bloqueado): sin él no hay aviso y listo.
export function showOnNextPage(notice) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...notice, at: Date.now() }));
  } catch {
    /* sin aviso en la página siguiente */
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

// Los avisos que Django dejó en la página. Se leen y se quitan de ella: desde ahora los muestra SweetAlert2.
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

// Si otra ventana ya está abierta (la de los errores de un formulario, por ejemplo), se espera a que se cierre:
// SweetAlert2 muestra una sola a la vez y abrir otra cerraría la primera.
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
