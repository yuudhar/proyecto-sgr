import { alerta, aviso } from "./alerts.js";

const form = document.querySelector("[data-context-form]");
const select = form ? form.querySelector("[data-context-select]") : null;

let ready = document.readyState === "complete";
if (!ready) {
  window.addEventListener("load", () => setTimeout(() => (ready = true), 0), { once: true });
}

function markDirty(event) {
  if (!ready) return;
  const guarded = event.target instanceof Element ? event.target.closest("form[data-unsaved-guard]") : null;
  if (guarded) guarded.dataset.dirty = "1";
}

document.addEventListener("input", markDirty);
document.addEventListener("change", markDirty);

export function formsWithUnsavedChanges() {
  return [...document.querySelectorAll("form[data-unsaved-guard]")].filter(
    (guarded) => guarded.dataset.unsavedGuard === "dirty" || guarded.dataset.dirty === "1",
  );
}

function optionText(value) {
  const option = select ? [...select.options].find((item) => item.value === value) : null;
  return option ? option.textContent.trim() : "";
}

if (form && select) {
  const button = form.querySelector(".context-apply");
  if (button) button.hidden = true;

  select.addEventListener("change", async () => {
    if (select.value === select.dataset.current) return;
    if (formsWithUnsavedChanges().length === 0) {
      form.requestSubmit();
      return;
    }
    const answer = await alerta.fire({
      icon: "warning",
      title: "Tienes cambios sin guardar",
      text:
        `Si cambias a «${optionText(select.value)}», lo que escribiste en este formulario se pierde: ` +
        "la pantalla se carga de nuevo con los datos de esa delegación.",
      showCancelButton: true,
      confirmButtonText: "Cambiar de delegación",
      cancelButtonText: "Seguir editando",
      focusCancel: true,
    });
    if (answer.isConfirmed) {
      form.requestSubmit();
      return;
    }
    select.value = select.dataset.current;
    aviso.fire({
      icon: "info",
      title: "Delegación sin cambios",
      text: `Sigues en «${optionText(select.dataset.current)}» y tus datos siguen en el formulario.`,
    });
  });
}
