// Estados de carga: mientras se envía un formulario, se busca en un listado o llega la ventana de un formulario, el
// botón (o enlace) que se apretó muestra un indicador de progreso y queda desactivado. Así se ve que algo está
// pasando y un doble clic no envía dos veces lo mismo.
//
//   form[data-once]       formulario que se envía (POST): los botones de enviar quedan desactivados
//   form[data-loading]    formulario de consulta (GET: buscar, filtrar): igual, y el panel de resultados queda «ocupado»
//   button[data-no-busy]  este botón no cambia (por ejemplo «Exportar a Excel»: descarga un archivo y la página no cambia)
//
// Sin JavaScript todo funciona igual, solo que sin el indicador. Si otro script frena el envío (la validación del
// formulario, una confirmación), los botones se dejan como estaban: el indicador solo sale cuando de verdad se envía.

const SPINNER_CLASS = "busy-spinner";
const STATUS_ATTR = "data-busy-status";

function spinner() {
  const dot = document.createElement("span");
  dot.className = `spinner-border spinner-border-sm ${SPINNER_CLASS}`;
  dot.setAttribute("aria-hidden", "true");
  return dot;
}

// Marca un botón o enlace como ocupado: indicador en lugar de su ícono, desactivado y con aria-busy.
export function start(control) {
  if (!control || control.dataset.busy === "1") return;
  control.dataset.busy = "1";
  control.setAttribute("aria-busy", "true");
  const icon = control.querySelector(":scope > i.bi");
  if (icon) {
    icon.classList.add("d-none");
    icon.before(spinner());
  } else {
    const dot = spinner();
    dot.dataset.gap = "1"; // lleva un espacio detrás, que se quita junto con él
    control.prepend(dot, " ");
  }
  if (control.matches("button, input")) {
    control.disabled = true;
  } else {
    control.classList.add("disabled"); // un enlace no se desactiva: se le quita el clic
    control.setAttribute("aria-disabled", "true");
  }
}

// Deja el botón o enlace como estaba.
export function stop(control) {
  if (!control || control.dataset.busy !== "1") return;
  delete control.dataset.busy;
  control.removeAttribute("aria-busy");
  control.querySelectorAll(`:scope > .${SPINNER_CLASS}`).forEach((dot) => {
    if (dot.dataset.gap && dot.nextSibling && dot.nextSibling.nodeType === Node.TEXT_NODE) dot.nextSibling.remove();
    dot.remove();
  });
  const icon = control.querySelector(":scope > i.bi.d-none");
  if (icon) icon.classList.remove("d-none");
  if (control.matches("button, input")) {
    control.disabled = false;
  } else {
    control.classList.remove("disabled");
    control.removeAttribute("aria-disabled");
  }
}

// Un formulario que se está enviando: todos sus botones de enviar se desactivan y el que se apretó (o el primero)
// muestra el indicador. Un lector de pantalla recibe un aviso de «Procesando…».
export function lock(form, submitter = null) {
  const buttons = [...form.querySelectorAll("button[type=submit]")];
  const main = submitter && buttons.includes(submitter) ? submitter : buttons[0];
  buttons.forEach((button) => (button === main ? start(button) : (button.disabled = true)));
  form.setAttribute("aria-busy", "true");
  if (!form.querySelector(`[${STATUS_ATTR}]`)) {
    const status = document.createElement("span");
    status.className = "visually-hidden";
    status.setAttribute("role", "status");
    status.setAttribute(STATUS_ATTR, "");
    status.textContent = "Procesando…";
    form.append(status);
  }
  return buttons;
}

// Vuelve el formulario a como estaba (el envío no llegó al servidor, o se volvió con el botón «atrás»).
export function unlock(form) {
  form.querySelectorAll("button[type=submit]").forEach((button) => {
    stop(button);
    button.disabled = false;
  });
  form.removeAttribute("aria-busy");
  form.querySelectorAll(`[${STATUS_ATTR}]`).forEach((status) => status.remove());
  const panel = form.closest(".panel");
  if (panel) {
    panel.classList.remove("is-loading");
    panel.removeAttribute("aria-busy");
  }
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !(form.hasAttribute("data-once") || form.hasAttribute("data-loading"))) return;
  const submitter = event.submitter;
  if (submitter && submitter.hasAttribute("data-no-busy")) return;
  // Se espera a que terminen los demás controladores del envío: si alguno lo frenó, no hay nada que mostrar. Los datos
  // del formulario ya se tomaron cuando corre esto, así que desactivar los botones no los afecta.
  window.setTimeout(() => {
    if (event.defaultPrevented) return;
    lock(form, submitter);
    if (form.hasAttribute("data-loading")) {
      const panel = form.closest(".panel");
      if (panel) {
        panel.classList.add("is-loading");
        panel.setAttribute("aria-busy", "true");
      }
    }
  }, 0);
});

// Al volver con el botón «atrás» del navegador la página puede volver tal como estaba al salir (con los botones
// ocupados): se dejan activos otra vez.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    document.querySelectorAll("form[data-once], form[data-loading]").forEach(unlock);
  }
});
