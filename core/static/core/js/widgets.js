import * as dialog from "./dialog.js";
import { initSearchable } from "./searchable-select.js";

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

function setUpColor(box) {
  const text = box.querySelector("input:not([type=color])");
  const picker = box.querySelector("[data-color-picker]");
  const swatch = box.querySelector(".color-swatch");

  function showColor() {
    const value = text.value.trim();
    if (HEX_COLOR.test(value)) {
      swatch.style.setProperty("--swatch", value);
      picker.value = value.toLowerCase();
    } else {
      swatch.style.removeProperty("--swatch");
    }
  }

  picker.hidden = false;
  picker.addEventListener("input", () => {
    text.value = picker.value;
    showColor();
    text.dispatchEvent(new Event("input", { bubbles: true }));
  });
  text.addEventListener("input", showColor);
  showColor();
}

const plain = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function matches(haystack, wanted) {
  const text = plain(haystack);
  if (text.includes(wanted)) return true;
  return /^[0-9.kK-]+$/.test(wanted) && text.replace(/\./g, "").includes(wanted.replace(/\./g, ""));
}

function lookupView(title, options, onChoose, searchLabel = "Buscar por nombre o cargo") {
  const view = document.createElement("div");
  view.className = "modal-content";
  view.innerHTML = `
    <div class="modal-header">
      <h2 class="modal-title" id="sgr-modal-title"></h2>
      <button type="button" class="btn-close" data-dialog-close aria-label="Cerrar el buscador"></button>
    </div>
    <div class="modal-body">
      <input type="search" class="form-control lookup-filter" aria-label="Buscar en la lista" autocomplete="off">
      <div class="list-group lookup-list"></div>
    </div>`;
  view.querySelector(".modal-title").textContent = title;
  const filter = view.querySelector(".lookup-filter");
  filter.placeholder = searchLabel;
  const list = view.querySelector(".lookup-list");

  function draw() {
    const wanted = plain(filter.value.trim());
    const shown = options.filter((option) => matches(`${option.value} ${option.detail}`, wanted));
    list.replaceChildren(
      ...shown.map((option) => {
        const choice = document.createElement("button");
        choice.type = "button";
        choice.className = "list-group-item list-group-item-action lookup-choice";
        const name = document.createElement("strong");
        name.textContent = option.value;
        const detail = document.createElement("span");
        detail.textContent = option.detail;
        choice.append(name, detail);
        choice.addEventListener("click", () => onChoose(option.value));
        return choice;
      }),
    );
    if (shown.length === 0) {
      const empty = document.createElement("p");
      empty.className = "lookup-empty";
      empty.textContent = options.length === 0 ? "No hay opciones en la lista. Escribe el nombre a mano." : "Ninguna opción coincide.";
      list.append(empty);
    }
  }

  filter.addEventListener("input", draw);
  draw();
  return view;
}

function setUpLookup(box, root) {
  const input = box.querySelector("input");
  const button = box.querySelector("[data-lookup-open]");
  const options = [...box.querySelectorAll("datalist option")].map((option) => ({
    value: option.value,
    detail: option.getAttribute("label") || "",
  }));
  const label = root.querySelector(`label[for="${input.id}"]`);
  const name = label ? label.textContent.replace("*", "").replace("(obligatorio)", "").trim() : "Lista";

  button.hidden = false;
  button.addEventListener("click", () => {
    const view = lookupView(
      `Buscar: ${name}`,
      options,
      (value) => {
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        dialog.back();
        if (input.isConnected) input.focus();
      },
      box.dataset.searchLabel || undefined,
    );
    dialog.push(view, input);
  });
}

function setUpPermissions(box) {
  const tools = box.querySelector("[data-perm-tools]");
  const checks = () => [...box.querySelectorAll(".perm-check")];
  if (tools) {
    tools.hidden = false;
    tools.addEventListener("click", (event) => {
      const button = event.target.closest("[data-perm-set]");
      if (!button) return;
      const mode = button.dataset.permSet;
      checks().forEach((check) => {
        check.checked = mode === "all" || (mode === "view" && check.dataset.action === "view");
      });
      box.classList.remove("is-invalid");
    });
  }
  box.addEventListener("change", (event) => {
    const check = event.target.closest(".perm-check");
    if (!check) return;
    const row = check.closest("tr");
    const view = row.querySelector('.perm-check[data-action="view"]');
    if (!view) return;
    if (check.dataset.action !== "view" && check.checked) view.checked = true;
    if (check.dataset.action === "view" && !check.checked) {
      row.querySelectorAll(".perm-check").forEach((other) => (other.checked = false));
    }
    box.classList.remove("is-invalid");
  });
}

function setUpDependent(select, root) {
  const parent = root.querySelector(`#${CSS.escape(select.dataset.dependsOn)}`);
  if (!parent) return;
  const options = [...select.options].filter((option) => option.value !== "");
  const placeholder = select.querySelector('option[value=""]') || new Option("", "");
  const choose = placeholder.textContent;
  const wasRequired = select.required || select.hasAttribute("data-choose-if-options");
  const note = document.createElement("div");
  note.className = "form-text dependent-note";
  note.setAttribute("role", "status");
  note.setAttribute("aria-live", "polite");
  select.insertAdjacentElement("afterend", note);

  options.forEach((option) => {
    if (option.dataset.name) option.textContent = option.dataset.name;
  });

  function refresh(announce) {
    const chosen = parent.value;
    const current = select.value;
    const valid = chosen ? options.filter((option) => option.dataset.parent === chosen) : [];
    select.replaceChildren(placeholder, ...valid);

    let message = "";
    if (!chosen) {
      placeholder.textContent = select.dataset.emptyParent || choose;
    } else if (valid.length === 0) {
      placeholder.textContent = select.dataset.emptyChildren || choose;
    } else {
      placeholder.textContent = choose;
    }
    const stays = valid.some((option) => option.value === current);
    select.value = stays ? current : "";
    if (announce && current && !stays) message = select.dataset.clearedMessage || "Se limpió la selección porque cambió la lista de la que depende.";
    select.disabled = valid.length === 0;
    select.required = wasRequired && valid.length > 0;
    note.textContent = message;
    select.classList.remove("is-invalid");
    select.removeAttribute("aria-invalid");
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  parent.addEventListener("change", () => refresh(true));
  refresh(false);
}

function setUpPasswordToggle(input) {
  if (input.closest(".password-field") || input.hasAttribute("data-no-reveal")) return;
  const group = document.createElement("div");
  group.className = "input-group password-field";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-outline-secondary password-toggle";
  const icon = document.createElement("i");
  icon.className = "bi bi-eye";
  icon.setAttribute("aria-hidden", "true");
  button.append(icon);
  if (input.id) button.setAttribute("aria-controls", input.id);

  function show(visible) {
    input.type = visible ? "text" : "password";
    icon.className = visible ? "bi bi-eye-slash" : "bi bi-eye";
    button.setAttribute("aria-pressed", visible ? "true" : "false");
    const label = visible ? "Ocultar contraseña" : "Mostrar contraseña";
    button.setAttribute("aria-label", label);
    button.title = label;
  }

  input.replaceWith(group);
  group.append(input, button);
  show(false);
  button.addEventListener("click", () => {
    show(input.type === "password");
    input.focus();
  });
  if (input.form) input.form.addEventListener("submit", () => show(false));
  window.addEventListener("pagehide", () => show(false));
}

export function initWidgets(root = document) {
  root.querySelectorAll("input[type=password]").forEach(setUpPasswordToggle);
  root.querySelectorAll("[data-color-field]").forEach(setUpColor);
  root.querySelectorAll(".perm-field").forEach(setUpPermissions);
  root.querySelectorAll("select[data-depends-on]").forEach((select) => setUpDependent(select, root));
  initSearchable(root);
  if (dialog.available) root.querySelectorAll("[data-lookup-field]").forEach((box) => setUpLookup(box, root));
}

initWidgets();
