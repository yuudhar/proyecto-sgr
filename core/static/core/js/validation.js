import { alerta } from "./alerts.js";

const NORMALIZERS = {
  spaces: (text) => text.replace(/\s+/g, " ").trim(),
  trim: (text) => text.trim(),
  nospaces: (text) => text.replace(/\s+/g, ""),
  upper: (text) => text.trim().toUpperCase(),
  lines: (text) => text.replace(/\r\n?/g, "\n").trim(),
  none: (text) => text,
  rut: (text) => {
    const clean = text.replace(/\s+/g, " ").trim().replace(/[.\s-]/g, "").toUpperCase();
    return clean.length > 1 ? `${clean.slice(0, -1)}-${clean.slice(-1)}` : clean;
  },
};

function rutDigit(body) {
  let total = 0;
  let factor = 2;
  for (const digit of [...body].reverse()) {
    total += Number(digit) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const rest = 11 - (total % 11);
  if (rest === 11) return "0";
  return rest === 10 ? "K" : String(rest);
}

const CHECKS = {
  rut: (text) => {
    const cut = text.indexOf("-");
    const body = cut === -1 ? text : text.slice(0, cut);
    const digit = cut === -1 ? "" : text.slice(cut + 1);
    return /^[0-9]+$/.test(body) && rutDigit(body) === digit;
  },
};

function labelOf(field) {
  if (field.hasAttribute("data-label")) return field.dataset.label;
  const label = field.id ? document.querySelector(`label[for="${field.id}"]`) : null;
  if (!label) return field.getAttribute("aria-label") || "";
  const copy = label.cloneNode(true);
  copy.querySelectorAll(".required-mark, .visually-hidden").forEach((part) => part.remove());
  return copy.textContent.trim();
}

function decimalsOf(step) {
  if (!step || step === "any") return null;
  const point = step.indexOf(".");
  return point === -1 ? 0 : step.length - point - 1;
}

function dayText(iso) {
  const [year, month, day] = iso.split("-");
  return day && month && year ? `${day}/${month}/${year}` : iso;
}

const plural = (count, one, many) => (count === 1 ? one : many);

function fileProblem(field) {
  const file = field.files && field.files[0];
  if (!file) return field.required ? "Elige un archivo." : "";
  const allowed = (field.accept || "").split(",").map((part) => part.trim().toLowerCase()).filter(Boolean);
  const extension = `.${file.name.split(".").pop().toLowerCase()}`;
  if (allowed.length && !allowed.includes(extension)) {
    return `Ese tipo de archivo no se acepta. Sube un archivo ${field.dataset.acceptLabel || allowed.join(", ")}.`;
  }
  const limit = Number(field.dataset.maxMb || 0);
  if (limit && file.size > limit * 1024 * 1024) return `El archivo pesa más de ${limit} MB.`;
  if (file.size === 0) return "El archivo está vacío.";
  return "";
}

function problemOf(field, form) {
  const skip = ["hidden", "submit", "button", "checkbox", "radio", "color"];
  if (field.disabled || skip.includes(field.type)) return "";
  if (field.type === "file") return fileProblem(field);

  const isSelect = field.tagName === "SELECT";
  let value = field.value;
  if (!isSelect && field.type !== "password") {
    const fix = NORMALIZERS[field.dataset.normalize];
    if (fix) {
      const fixed = fix(value);
      if (fixed !== value) {
        field.value = fixed;
        value = fixed;
      }
    }
  }

  if (field.validity.badInput) {
    return field.type === "date" ? "Escribe una fecha válida." : "Escribe un número válido.";
  }

  const isBlank = isSelect ? value === "" : value.trim() === "";
  if (isBlank) {
    if (!field.required) return "";
    if (field.dataset.requiredMessage) return field.dataset.requiredMessage;
    return isSelect ? "Elige una opción." : "Este campo es obligatorio.";
  }
  if (isSelect) return "";

  const pattern = field.dataset.pattern;
  if (pattern && !new RegExp(`^(?:${pattern})$`).test(value)) {
    return field.dataset.message || "El formato no es válido.";
  }
  const check = CHECKS[field.dataset.check];
  if (check && !check(value)) return field.dataset.message || "El valor no es válido.";

  if (field.maxLength > 0 && value.length > field.maxLength) {
    return `Escribe como máximo ${field.maxLength} ${plural(field.maxLength, "carácter", "caracteres")}.`;
  }
  if (field.minLength > 0 && value.length < field.minLength) {
    return `Escribe al menos ${field.minLength} ${plural(field.minLength, "carácter", "caracteres")}.`;
  }
  if (field.type === "email" && field.validity.typeMismatch) {
    return "Escribe un correo válido, por ejemplo nombre@dominio.cl.";
  }
  if (field.type === "date") {
    if (field.min && value < field.min) return `La fecha no puede ser anterior al ${dayText(field.min)}.`;
    if (field.max && value > field.max) {
      return field.dataset.maxMessage || `La fecha no puede ser posterior al ${dayText(field.max)}.`;
    }
    const earlier = field.dataset.notBefore ? form.querySelector(`#${field.dataset.notBefore}`) : null;
    if (earlier && earlier.value && value < earlier.value) {
      return field.dataset.notBeforeMessage || "La fecha no puede ser anterior a la de partida.";
    }
  }
  if (field.type === "number") {
    const number = Number(value);
    if (Number.isNaN(number)) return "Escribe un número válido.";
    if (field.min !== "" && number < Number(field.min)) return `El valor mínimo es ${field.min}.`;
    if (field.max !== "" && number > Number(field.max)) return `El valor máximo es ${field.max}.`;
    const decimals = decimalsOf(field.step);
    if (decimals !== null) {
      const written = value.includes(".") ? value.length - value.indexOf(".") - 1 : 0;
      if (written > decimals) {
        return decimals === 0
          ? "Escribe un número entero."
          : `Usa como máximo ${decimals} ${plural(decimals, "decimal", "decimales")}.`;
      }
    }
  }

  if (field.dataset.match) {
    const other = form.querySelector(`#${field.dataset.match}`);
    if (other && other.value !== value) return "Las dos contraseñas deben ser iguales.";
  }
  return "";
}

function errorBoxOf(field) {
  return (field.id && document.getElementById(`${field.id}_error`)) || document.getElementById(`id_${field.name}_error`);
}

function paint(field, message) {
  const box = errorBoxOf(field);
  field.classList.toggle("is-invalid", Boolean(message));
  if (message) field.setAttribute("aria-invalid", "true");
  else field.removeAttribute("aria-invalid");
  if (box) {
    box.textContent = message;
    box.classList.toggle("d-block", Boolean(message));
  }
}

function radioProblems(form) {
  const found = [];
  const seen = new Set();
  form.querySelectorAll("input[type=radio][required]").forEach((radio) => {
    if (seen.has(radio.name)) return;
    seen.add(radio.name);
    const group = [...form.querySelectorAll(`input[type=radio][name="${radio.name}"]`)];
    const box = document.getElementById(`id_${radio.name}_error`);
    const missing = !group.some((item) => item.checked);
    if (box) {
      box.textContent = missing ? "Elige una opción." : "";
      box.classList.toggle("d-block", missing);
    }
    if (missing) {
      const legend = radio.closest("fieldset")?.querySelector("legend");
      const copy = legend ? legend.cloneNode(true) : null;
      if (copy) copy.querySelectorAll(".required-mark, .visually-hidden").forEach((part) => part.remove());
      found.push({ field: group[0], label: copy ? copy.textContent.trim() : "", message: "Elige una opción." });
    }
  });
  return found;
}

function problemsOf(form) {
  const problems = [];
  form.querySelectorAll("input, select, textarea").forEach((field) => {
    const message = problemOf(field, form);
    paint(field, message);
    if (message) problems.push({ field, label: labelOf(field), message });
  });
  return problems.concat(radioProblems(form));
}

function listOf(problems) {
  const list = document.createElement("ul");
  list.className = "swal-problems";
  problems.forEach(({ label, message }) => {
    const item = document.createElement("li");
    if (label) {
      const name = document.createElement("strong");
      name.textContent = `${label}: `;
      item.append(name);
    }
    item.append(message);
    list.append(item);
  });
  return list;
}

function showProblems(problems, title) {
  const box = document.createElement("div");
  const intro = document.createElement("p");
  intro.textContent = "Corrige esto para continuar:";
  box.append(intro, listOf(problems));
  const first = problems.find((problem) => problem.field);
  return alerta.fire({
    icon: "error",
    title,
    html: box,
    didClose: () => {
      if (first && typeof first.field.focus === "function") first.field.focus();
    },
  });
}

export function setUp(form, scope = document) {
  const title = form.dataset.validateTitle || "Revisa el formulario";
  form.noValidate = true;

  form.addEventListener("mousedown", (event) => {
    if (event.target.closest("button, .btn")) event.preventDefault();
  });

  form.addEventListener("submit", (event) => {
    const button = event.submitter;
    if (button && (button.hasAttribute("data-skip-validate") || button.hasAttribute("formnovalidate"))) {
      return;
    }
    const problems = problemsOf(form);
    if (problems.length === 0) return;
    event.preventDefault();
    showProblems(problems, title);
  });

  form.querySelectorAll(".is-invalid").forEach((field) => {
    field.dataset.fromServer = "1";
  });

  form.addEventListener("focusout", (event) => {
    const field = event.target;
    if (field.matches("input, select, textarea") && !field.dataset.fromServer) paint(field, problemOf(field, form));
  });
  form.addEventListener("input", (event) => {
    const field = event.target;
    delete field.dataset.fromServer;
    if (field.classList.contains("is-invalid")) paint(field, problemOf(field, form));
  });

  showServerErrors(form, form.dataset.errorTitle || title, scope);
}

function showServerErrors(form, title, scope) {
  const problems = [];
  scope.querySelectorAll("[data-form-error]").forEach((box) => {
    problems.push({ field: null, label: "", message: box.textContent.trim() });
  });
  const seen = new Set();
  form.querySelectorAll(".is-invalid").forEach((field) => {
    const box = errorBoxOf(field);
    const message = box ? box.textContent.trim() : "";
    if (message && !seen.has(box)) {
      seen.add(box);
      problems.push({ field, label: labelOf(field), message });
    }
  });
  if (problems.length > 0) showProblems(problems, title);
}

document.addEventListener("mousedown", (event) => {
  const field = document.activeElement;
  if (event.target.closest("a[href]") && field && field.form && field.form.matches("form[data-validate]")) {
    event.preventDefault();
  }
});

document.querySelectorAll("form[data-validate]").forEach((form) => setUp(form));
