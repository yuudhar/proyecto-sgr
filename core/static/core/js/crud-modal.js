// Nuevo y Editar en una ventana modal (Bootstrap), sin salir del listado.
//
// Los enlaces con data-modal-form siguen siendo enlaces normales: sin JavaScript, o abriéndolos en otra
// pestaña, llevan a la página del formulario. Con JavaScript:
//   1. se le pide a Django el formulario con ?modal=1 (solo el contenido de la ventana);
//   2. se muestra en la ventana y se le agregan la validación y los campos especiales;
//   3. al guardar se envía con fetch. Si el servidor devuelve errores, se muestra otra vez el formulario
//      con sus mensajes y la ventana de SweetAlert2; si se guardó, se recarga la página para ver el cambio.

import { alerta, aviso } from "./alerts.js";
import * as busy from "./busy.js";
import * as dialog from "./dialog.js";
import { setUp } from "./validation.js";
import { initWidgets } from "./widgets.js";

// Un clic normal, sin teclas: abrir el enlace en otra pestaña sigue funcionando.
const isPlainClick = (event) => event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;

let changed = false; // se guardó algo con la ventana abierta: al cerrarla se recarga la página
let opening = false; // ya se está pidiendo un formulario: un segundo clic no abre otro

// La misma dirección con ?modal=1 (conserva lo que ya traía, como ?beneficiary=3).
function modalUrl(url) {
  const address = new URL(url, window.location.href);
  address.searchParams.set("modal", "1");
  return address.pathname + address.search;
}

function failed(text) {
  return alerta.fire({ icon: "error", title: "No se pudo guardar", text });
}

// Convierte el HTML que mandó Django en un formulario con sus campos especiales listos.
function toForm(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  const form = template.content.firstElementChild;
  initWidgets(form);
  return form;
}

// Pide el formulario y lo abre en la ventana. Devuelve false si no llegó (permiso, sesión vencida...).
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
  // «Guardar y agregar otro»: el formulario nuevo parte vacío y un aviso corto cuenta que el anterior sí se guardó.
  // El servidor solo manda este texto cuando guardó.
  if (notice) aviso.fire({ icon: "success", title: notice });
  // La validación va primero: si el formulario llegó con errores, la ventana de aviso los muestra, y al
  // enviar frena el envío si encuentra problemas. El envío con fetch se agrega después, para que corra
  // solo cuando la validación lo dejó pasar.
  setUp(form, form);
  form.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return;
    event.preventDefault();
    send(form, event.submitter);
  });
}

async function send(form, button) {
  const data = new FormData(form, button); // antes de desactivar los botones: uno desactivado no viaja en el envío
  busy.lock(form, button); // indicador de «guardando» y sin doble envío mientras llega la respuesta
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
    show(await response.text()); // volvió con errores
  } else if (kind === "saved") {
    const result = await response.json();
    if (result.again) {
      // "Guardar y agregar otro": otro formulario vacío en la misma ventana, con el aviso arriba.
      changed = true;
      if (!(await openForm(result.create_url, result.message))) window.location.reload();
    } else {
      window.location.reload(); // la página muestra el aviso de siempre y el cambio
    }
  } else {
    busy.unlock(form);
    // 403 o una redirección al inicio de sesión: la sesión venció o falta permiso. Otro código es una falla del
    // servidor, y ahí conviene reintentar sin recargar, para no perder lo escrito.
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
  if (opening) return; // un segundo clic mientras llega el formulario no abre la página completa
  opening = true;
  busy.start(link); // indicador de carga en el botón mientras llega el formulario
  let opened = false;
  try {
    opened = await openForm(link.href);
  } finally {
    opening = false;
    busy.stop(link);
  }
  if (!opened) window.location.href = link.href; // sin ventana, la página normal
});
