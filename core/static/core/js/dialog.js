// Ventana modal compartida (Bootstrap 5): aquí se abren los formularios de Nuevo y Editar y el buscador
// de las listas (por ejemplo, el del Encargado de una delegación).
//
// Bootstrap no permite dos modales abiertos a la vez, así que hay una sola ventana. Cuando algo se abre
// encima de otra cosa (el buscador sobre un formulario), lo de abajo se guarda tal como está, con lo que
// se alcanzó a escribir, y vuelve cuando se cierra lo de arriba.

const element = document.getElementById("sgr-modal");
const frame = element ? element.querySelector(".modal-dialog") : null;
// "static" y sin teclado: un clic fuera de la ventana no la cierra y se pierden menos datos escritos.
const modal = element && window.bootstrap ? new window.bootstrap.Modal(element, { backdrop: "static", keyboard: false }) : null;

const below = []; // contenidos que quedaron debajo del actual, con su posición de scroll y su foco
const closedListeners = [];
let visible = false;
let opener = null; // lo que tenía el foco antes de abrir la ventana, para devolvérselo al cerrarla

export const available = modal !== null;

// Pone el cursor en el primer campo del contenido.
function focusFirst(content) {
  const field = content.querySelector("[autofocus], input:not([type=hidden]):not([disabled]), select, textarea");
  (field || content).focus();
}

function place(content) {
  frame.replaceChildren(content);
}

// Abre la ventana con un contenido (un elemento con la clase modal-content). Lo que hubiera, se descarta.
// returnTo es lo que recibe el foco al cerrar la ventana (por defecto, lo que lo tenía al abrirla).
export function open(content, returnTo = null) {
  if (!modal) return false;
  below.length = 0;
  place(content);
  if (visible) {
    focusFirst(content);
  } else {
    opener = returnTo || document.activeElement;
    modal.show();
  }
  return true;
}

// Muestra otro contenido encima del actual; el actual vuelve con back().
export function push(content, returnTo = null) {
  if (!modal) return false;
  if (!visible) return open(content, returnTo);
  const current = frame.firstElementChild;
  const body = current.querySelector(".modal-body");
  below.push({ content: current, scroll: body ? body.scrollTop : 0, focus: document.activeElement });
  place(content);
  focusFirst(content);
  return true;
}

// Vuelve al contenido de abajo; si no hay ninguno, cierra la ventana.
export function back() {
  const previous = below.pop();
  if (!previous) {
    close();
    return;
  }
  place(previous.content);
  const body = previous.content.querySelector(".modal-body");
  if (body) body.scrollTop = previous.scroll;
  if (previous.focus && previous.focus.isConnected) previous.focus.focus();
}

export function close() {
  if (modal && visible) modal.hide();
}

// Pide que se ejecute una función cada vez que la ventana termina de cerrarse.
export function onClosed(listener) {
  closedListeners.push(listener);
}

if (element) {
  element.addEventListener("show.bs.modal", () => {
    visible = true;
  });
  element.addEventListener("shown.bs.modal", () => {
    // Si ya se abrió una ventana de aviso (por ejemplo, con los errores del formulario), el foco es de ella.
    if (frame.firstElementChild && !document.querySelector(".swal2-popup")) focusFirst(frame.firstElementChild);
  });
  element.addEventListener("hidden.bs.modal", () => {
    visible = false;
    frame.replaceChildren();
    below.length = 0;
    if (opener && opener.isConnected) opener.focus();
    opener = null;
    closedListeners.forEach((listener) => listener());
  });
  // Un clic fuera de la ventana no hace nada (sin el "rebote" que Bootstrap le agrega).
  element.addEventListener("hidePrevented.bs.modal", (event) => event.preventDefault());
  // Los botones de cerrar y Cancelar llevan data-dialog-close; Escape hace lo mismo.
  element.addEventListener("click", (event) => {
    if (event.target.closest("[data-dialog-close]")) back();
  });
  element.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      back();
    }
  });
}
