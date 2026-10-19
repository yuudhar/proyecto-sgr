const SPINNER_CLASS = "busy-spinner";
const STATUS_ATTR = "data-busy-status";

function spinner() {
  const dot = document.createElement("span");
  dot.className = `spinner-border spinner-border-sm ${SPINNER_CLASS}`;
  dot.setAttribute("aria-hidden", "true");
  return dot;
}

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
    dot.dataset.gap = "1";
    control.prepend(dot, " ");
  }
  if (control.matches("button, input")) {
    control.disabled = true;
  } else {
    control.classList.add("disabled");
    control.setAttribute("aria-disabled", "true");
  }
}

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

window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    document.querySelectorAll("form[data-once], form[data-loading]").forEach(unlock);
  }
});
