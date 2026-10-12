// Selector de delegación de la franja de arriba (A2). Con JavaScript el selector cambia la delegación en cuanto se
// elige una y el botón «Cambiar» se oculta; sin JavaScript queda el botón y todo funciona igual.
//
// SweetAlert2 solo avisa: la delegación elegida la guarda y la comprueba el servidor (POST a «contexto/»), que
// responde 403 si no está autorizada para la persona. Aquí solo se evita perder lo escrito sin querer:
//
//   data-unsaved-guard   en un <form> de la página: si tiene datos escritos que no se guardaron, cambiar de delegación
//                        pregunta antes, porque la pantalla se vuelve a cargar con los datos de la delegación nueva.
//                        Con el valor «dirty» el formulario ya llega con datos (por ejemplo, tras un error).

import { alerta, aviso } from "./alerts.js";

const form = document.querySelector("[data-context-form]");
const select = form ? form.querySelector("[data-context-select]") : null;

// Los eventos que el propio código dispara al armar la página (listas que dependen de otra, por ejemplo) no cuentan
// como cambios de la persona: se miran solo cuando la página terminó de cargar.
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

// Formularios de la página con datos escritos que todavía no se guardan.
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
