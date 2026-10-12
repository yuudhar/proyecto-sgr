// Confirmaciones y cancelaciones con SweetAlert2. SweetAlert2 solo pregunta o avisa: quien decide y quien guarda
// es siempre el servidor, que vuelve a comprobar el permiso, el token CSRF y los datos.
//
// 1. Eliminar con confirmación. El enlace «Eliminar» (data-delete trae el nombre del registro) abre una ventana y,
//    si se confirma, envía un POST normal con su token CSRF; así Django comprueba el permiso, elimina, redirige y
//    muestra su aviso de siempre. Sin JavaScript el enlace lleva a una página de confirmación que hace lo mismo.
//
//      data-delete-kind="archive"  el registro queda inactivo (borrado lógico) y se puede restaurar
//      data-delete-kind="remove"   el registro se borra de verdad (los roles)
//      data-blocked="..."          el registro está en uso: se explica por qué y no se ofrece eliminar
//
// 2. Confirmar un envío (data-confirm-submit en el formulario), por ejemplo al cambiar la contraseña. Si se
//    cancela, el formulario no se envía y un aviso lo dice. Los textos salen de los atributos data-confirm-*.
//
// 3. Cancelar un formulario (data-cancel-form="create" o "edit"): no se guarda nada y un aviso lo dice.

import { alerta, aviso } from "./alerts.js";
import { showOnNextPage } from "./flash.js";

// Un clic normal, sin teclas: abrir el enlace en otra pestaña sigue funcionando.
function isPlainClick(event) {
  return event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;
}

export function post(url) {
  const form = document.createElement("form");
  form.method = "post";
  form.action = url;
  const token = document.createElement("input");
  token.type = "hidden";
  token.name = "csrfmiddlewaretoken";
  token.value = document.querySelector('meta[name="csrf-token"]').content;
  form.append(token);
  document.body.append(form);
  form.submit();
}

document.addEventListener("click", async (event) => {
  const link = event.target.closest("a[data-delete]");
  if (!link || event.defaultPrevented || !isPlainClick(event)) return;
  event.preventDefault();
  const name = link.dataset.delete;
  const subject = name ? `«${name}»` : "El registro";

  if (link.dataset.blocked) {
    await alerta.fire({
      icon: "info",
      title: "No se puede eliminar",
      text: `${subject}: ${link.dataset.blocked}`,
      confirmButtonText: "Entendido",
    });
    return;
  }

  const remove = link.dataset.deleteKind === "remove";
  const answer = await alerta.fire({
    icon: "warning",
    title: remove ? "¿Eliminar definitivamente?" : "¿Eliminar registro?",
    text: remove
      ? `${subject} se elimina para siempre. Esta acción no se puede deshacer.`
      : `${subject} deja de aparecer en los listados y queda inactivo. No se borra: se puede restaurar cuando haga falta.`,
    showCancelButton: true,
    confirmButtonText: "Sí, eliminar",
    cancelButtonText: "Cancelar",
    focusCancel: true,
  });
  if (answer.isConfirmed) {
    post(link.href);
  } else {
    aviso.fire({ icon: "info", title: "Eliminación cancelada", text: "No se hizo ningún cambio." });
  }
});

// -- 2. Confirmar un envío ------------------------------------------------------------------------------

// Escucha en document (burbujeo): para cuando llega el envío, la validación del formulario ya corrió y, si encontró
// problemas, ya lo detuvo. Solo se pregunta cuando lo escrito está bien.
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-confirm-submit")) return;
  if (form.dataset.confirmed === "1") {
    delete form.dataset.confirmed; // ya se confirmó: este es el envío de verdad (o la validación lo frenó)
    return;
  }
  if (event.defaultPrevented) return;
  event.preventDefault();
  const submitter = event.submitter;
  const answer = await alerta.fire({
    icon: "question",
    title: form.dataset.confirmTitle || "¿Guardar los cambios?",
    text: form.dataset.confirmText || "",
    showCancelButton: true,
    confirmButtonText: form.dataset.confirmButton || "Sí, guardar",
    cancelButtonText: "Cancelar",
  });
  if (answer.isConfirmed) {
    form.dataset.confirmed = "1";
    form.requestSubmit(submitter || undefined);
  } else {
    aviso.fire({
      icon: "info",
      title: form.dataset.cancelTitle || "Cambio cancelado",
      text: form.dataset.cancelText || "No se guardó ningún cambio.",
    });
  }
});

// -- 3. Cancelar un formulario --------------------------------------------------------------------------

document.addEventListener("click", (event) => {
  const control = event.target.closest("[data-cancel-form]");
  if (!control || event.defaultPrevented) return;
  const creating = control.dataset.cancelForm !== "edit";
  const notice = {
    title: creating ? "Registro cancelado" : "Edición cancelada",
    text: creating ? "No se creó ningún registro." : "No se guardó ningún cambio.",
  };
  if (control.matches("a[href]")) {
    // En la página completa el enlace lleva a otra pantalla: el aviso lo muestra esa pantalla al cargar.
    if (isPlainClick(event)) showOnNextPage(notice);
  } else {
    // En la ventana modal la persona sigue en la misma pantalla: el aviso sale al instante.
    aviso.fire({ icon: "info", ...notice });
  }
});
