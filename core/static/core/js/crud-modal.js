import { alerta, aviso } from "./alerts.js";
import * as busy from "./busy.js";
import * as dialog from "./dialog.js";
import { setUp } from "./validation.js";
import { initWidgets } from "./widgets.js";

const isPlainClick = (event) => event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;

let changed = false;
let opening = false;

function modalUrl(url) {
  const address = new URL(url, window.location.href);
  address.searchParams.set("modal", "1");
  return address.pathname + address.search;
}

function failed(text) {
  return alerta.fire({ icon: "error", title: "No se pudo guardar", text });
}

function toForm(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  const form = template.content.firstElementChild;
  initWidgets(form);
  return form;
}

async function openForm(url, notice = "") {
  let response;
  try {
    response = await fetch(modalUrl(url), { headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" });
  } catch {
    return false;
  }
  if (!response.ok || response.headers.get("X-Modal") !== "form") return false;
  show(await response.text(), notice);
  return true;
}

function show(html, notice = "") {
  const form = toForm(html);
  dialog.open(form);
  if (notice) aviso.fire({ icon: "success", title: notice });
  setUp(form, form);
  form.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return;
    event.preventDefault();
    send(form, event.submitter);
  });
}

async function send(form, button) {
  const data = new FormData(form, button);
  busy.lock(form, button);
  let response;
  try {
    response = await fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    });
  } catch {
    busy.unlock(form);
    failed("No hay conexión con el servidor. Revisa tu red e inténtalo de nuevo.");
    return;
  }
  const kind = response.headers.get("X-Modal");
  if (kind === "form") {
    show(await response.text());
  } else if (kind === "saved") {
    const result = await response.json();
    if (result.again) {
      changed = true;
      if (!(await openForm(result.create_url, result.message))) window.location.reload();
    } else {
      window.location.reload();
    }
  } else {
    busy.unlock(form);
    const denied = response.status === 403 || response.redirected;
    failed(
      denied
        ? "Tu sesión pudo vencer o ya no tienes permiso para esto. Recarga la página e inténtalo otra vez."
        : "El servidor no pudo guardar los cambios. Espera un momento e inténtalo de nuevo: lo que escribiste sigue en la ventana.",
    );
  }
}

dialog.onClosed(() => {
  if (changed) window.location.reload();
});

document.addEventListener("click", async (event) => {
  const link = event.target.closest("a[data-modal-form]");
  if (!link || event.defaultPrevented || !isPlainClick(event) || !dialog.available) return;
  event.preventDefault();
  if (opening) return;
  opening = true;
  busy.start(link);
  let opened = false;
  try {
    opened = await openForm(link.href);
  } finally {
    opening = false;
    busy.stop(link);
  }
  if (!opened) window.location.href = link.href;
});
