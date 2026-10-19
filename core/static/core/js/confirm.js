import { alerta, aviso } from "./alerts.js";
import { showOnNextPage } from "./flash.js";

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

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-confirm-submit")) return;
  if (form.dataset.confirmed === "1") {
    delete form.dataset.confirmed;
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

document.addEventListener("click", (event) => {
  const control = event.target.closest("[data-cancel-form]");
  if (!control || event.defaultPrevented) return;
  const creating = control.dataset.cancelForm !== "edit";
  const notice = {
    title: creating ? "Registro cancelado" : "Edición cancelada",
    text: creating ? "No se creó ningún registro." : "No se guardó ningún cambio.",
  };
  if (control.matches("a[href]")) {
    if (isPlainClick(event)) showOnNextPage(notice);
  } else {
    aviso.fire({ icon: "info", ...notice });
  }
});
