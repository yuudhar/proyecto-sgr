// Selector con buscador. Cuando una lista tiene muchas opciones (cientos de actividades, funcionarios…)
// recorrerla con la rueda del mouse no sirve: este módulo deja escribir para filtrar.
//
// El <select> original sigue siendo el que manda: guarda el valor, viaja en el formulario y lo leen la validación y
// la búsqueda en vivo. Aquí solo se le pone encima una caja de texto con una lista desplegable que lo mantiene al día.
// Sin JavaScript (o con pocas opciones) el <select> se ve y funciona como siempre.
//
// Marcadores en el <select>:
//   data-searchable                   se activa si tiene MIN_OPTIONS opciones o más
//   data-searchable="always"          se activa siempre
//   data-searchable-min="<n>"         cambia el mínimo de opciones
//   data-search-label="<texto>"       texto de ayuda de la caja de búsqueda
const MIN_OPTIONS = 8;
const MAX_SHOWN = 60; // aunque haya miles de coincidencias, solo se dibujan estas; el resto se alcanza escribiendo más
let counter = 0;

const plain = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Todas las palabras escritas deben aparecer (en cualquier orden) y se ignoran tildes y mayúsculas.
export function matchesAll(text, wanted) {
  const haystack = plain(text);
  return plain(wanted)
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

export function setUpSearchable(select) {
  if (select.dataset.ssReady || select.multiple || select.hasAttribute("data-depends-on")) return;
  const always = select.dataset.searchable === "always";
  const minimum = Number(select.dataset.searchableMin || MIN_OPTIONS);
  if (!always && select.options.length < minimum) return;
  select.dataset.ssReady = "1";

  const id = `ss${++counter}`;
  const wrapper = document.createElement("div");
  wrapper.className = "ss";
  const box = document.createElement("div");
  box.className = "input-group ss-box";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "form-control ss-input";
  input.id = `${select.id || id}_buscar`;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", `${id}_lista`);
  input.setAttribute("autocomplete", "off");
  input.setAttribute("autocapitalize", "off");
  input.spellcheck = false;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "btn btn-outline-secondary ss-toggle";
  toggle.tabIndex = -1;
  toggle.setAttribute("aria-label", "Mostrar la lista");
  toggle.innerHTML = '<i class="bi bi-chevron-down" aria-hidden="true"></i>';
  box.append(input, toggle);

  const list = document.createElement("ul");
  list.className = "ss-list";
  list.id = `${id}_lista`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  const status = document.createElement("p");
  status.className = "visually-hidden";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  wrapper.append(box, list, status);

  select.classList.add("ss-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");
  select.after(wrapper);

  // El rótulo del campo apunta al <select>; se redirige a la caja de texto.
  const label = select.id ? document.querySelector(`label[for="${CSS.escape(select.id)}"]`) : null;
  if (label) {
    label.setAttribute("for", input.id);
    if (!label.id) label.id = `${id}_rotulo`;
    input.setAttribute("aria-labelledby", label.id);
  }
  const hint = select.getAttribute("aria-describedby");
  if (hint) input.setAttribute("aria-describedby", hint);
  if (select.dataset.label) input.dataset.label = select.dataset.label;

  let open = false;
  let typing = false; // true mientras la persona escribe: recién ahí se filtra la lista
  let active = -1;
  let shown = [];

  const blank = () => select.querySelector('option[value=""]');
  const optionsNow = () => [...select.options].filter((option) => option.value !== "");
  const labelOf = (option) => option.textContent.trim();

  function showSelected() {
    const chosen = select.selectedOptions[0];
    input.value = chosen && chosen.value !== "" ? labelOf(chosen) : "";
    input.placeholder = (blank() ? labelOf(blank()) : "") || select.dataset.searchLabel || "Escribe para buscar";
  }

  function syncState() {
    input.disabled = select.disabled;
    toggle.disabled = select.disabled;
    input.classList.toggle("is-invalid", select.classList.contains("is-invalid"));
    if (select.getAttribute("aria-invalid")) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
    if (select.required) input.setAttribute("aria-required", "true");
    else input.removeAttribute("aria-required");
    if (select.disabled) close(false);
  }

  function place() {
    const rect = input.closest(".ss-box").getBoundingClientRect();
    const room = window.innerHeight - rect.bottom;
    const wanted = Math.min(list.scrollHeight, 288);
    const above = room < Math.min(wanted, 200) && rect.top > room;
    list.style.left = `${rect.left}px`;
    list.style.width = `${rect.width}px`;
    list.style.maxHeight = `${Math.max(120, Math.min(288, (above ? rect.top : room) - 12))}px`;
    if (above) {
      list.style.top = "";
      list.style.bottom = `${window.innerHeight - rect.top + 2}px`;
    } else {
      list.style.bottom = "";
      list.style.top = `${rect.bottom + 2}px`;
    }
  }

  function draw() {
    const wanted = typing ? input.value.trim() : "";
    const found = optionsNow().filter((option) => !wanted || matchesAll(labelOf(option), wanted));
    shown = found.slice(0, MAX_SHOWN);
    const items = [];
    if (!select.required && blank() && !wanted) {
      items.push({ value: "", text: labelOf(blank()) || "Sin selección", empty: true });
    }
    shown.forEach((option) => items.push({ value: option.value, text: labelOf(option) }));
    const current = select.value;
    list.replaceChildren(
      ...items.map((item, index) => {
        const row = document.createElement("li");
        row.className = "ss-option";
        row.id = `${id}_op${index}`;
        row.setAttribute("role", "option");
        row.dataset.value = item.value;
        if (item.empty) row.classList.add("ss-empty-choice");
        const selected = item.value === current && item.value !== "";
        row.setAttribute("aria-selected", selected ? "true" : "false");
        row.textContent = item.text;
        return row;
      }),
    );
    if (found.length === 0) {
      const none = document.createElement("li");
      none.className = "ss-note";
      none.textContent = "Ninguna opción coincide con lo que escribiste.";
      list.append(none);
    } else if (found.length > shown.length) {
      const more = document.createElement("li");
      more.className = "ss-note";
      more.textContent = `Hay ${found.length - shown.length} coincidencias más: sigue escribiendo para acotar.`;
      list.append(more);
    }
    status.textContent =
      found.length === 0 ? "Sin coincidencias." : `${found.length} ${found.length === 1 ? "opción" : "opciones"}.`;
    const rows = [...list.querySelectorAll(".ss-option")];
    const start = rows.findIndex((row) => row.getAttribute("aria-selected") === "true");
    move(typing ? (rows.length ? (rows[0].classList.contains("ss-empty-choice") && rows.length > 1 ? 1 : 0) : -1) : start, false);
    place();
  }

  function move(index, scroll = true) {
    const rows = [...list.querySelectorAll(".ss-option")];
    rows.forEach((row) => row.classList.remove("is-active"));
    active = rows.length === 0 ? -1 : Math.max(0, Math.min(rows.length - 1, index));
    if (active === -1) {
      input.removeAttribute("aria-activedescendant");
      return;
    }
    rows[active].classList.add("is-active");
    input.setAttribute("aria-activedescendant", rows[active].id);
    if (scroll) rows[active].scrollIntoView({ block: "nearest" });
  }

  function openList() {
    if (open || select.disabled) return;
    open = true;
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    wrapper.classList.add("is-open");
    typing = false;
    draw();
    const selected = list.querySelector('[aria-selected="true"]');
    if (selected) selected.scrollIntoView({ block: "nearest" });
  }

  function close(restore = true) {
    if (!open) return;
    open = false;
    typing = false;
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    wrapper.classList.remove("is-open");
    if (restore) showSelected();
  }

  function choose(value) {
    const changed = select.value !== value;
    select.value = value;
    close();
    showSelected();
    if (changed) {
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  input.addEventListener("focus", () => input.select());
  input.addEventListener("click", openList);
  toggle.addEventListener("click", () => {
    if (open) close();
    else {
      input.focus();
      openList();
    }
  });
  input.addEventListener("input", (event) => {
    event.stopPropagation(); // lo escrito aquí solo busca en la lista; no es un dato del formulario
    typing = true;
    if (!open) openList();
    else draw();
  });
  input.addEventListener("keydown", (event) => {
    const rows = [...list.querySelectorAll(".ss-option")];
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      move(active + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Home" && open && event.ctrlKey) {
      event.preventDefault();
      move(0);
    } else if (event.key === "End" && open && event.ctrlKey) {
      event.preventDefault();
      move(rows.length - 1);
    } else if (event.key === "Enter") {
      if (open) {
        event.preventDefault(); // no enviar el formulario al elegir
        if (active >= 0 && rows[active]) choose(rows[active].dataset.value);
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        event.stopPropagation(); // que no cierre también el cuadro de diálogo
        close();
      }
    } else if (event.key === "Tab") {
      close();
    }
  });
  input.addEventListener("blur", () => {
    window.setTimeout(() => {
      if (!wrapper.contains(document.activeElement)) close();
    }, 0);
  });
  // mousedown y no click: así la caja no pierde el foco (y no cierra la lista) antes de elegir.
  list.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const row = event.target.closest(".ss-option");
    if (row) choose(row.dataset.value);
  });
  list.addEventListener("mousemove", (event) => {
    const row = event.target.closest(".ss-option");
    if (row) move([...list.querySelectorAll(".ss-option")].indexOf(row), false);
  });
  const reposition = () => {
    if (open) place();
  };
  window.addEventListener("resize", reposition);
  window.addEventListener("scroll", reposition, true);

  // Mantener la caja al día cuando el <select> cambia por otra vía (reiniciar, otro script, error del servidor…).
  select.addEventListener("change", () => {
    if (!open) showSelected();
  });
  select.addEventListener("focus", () => input.focus()); // la validación enfoca el campo con problemas
  new MutationObserver(() => {
    syncState();
    if (!open) showSelected();
  }).observe(select, {
    attributes: true,
    attributeFilter: ["disabled", "class", "required", "aria-invalid"],
    childList: true,
  });
  if (select.form) select.form.addEventListener("reset", () => window.setTimeout(showSelected, 0));

  showSelected();
  syncState();
}

export function initSearchable(root = document) {
  root.querySelectorAll("select[data-searchable]").forEach(setUpSearchable);
}
