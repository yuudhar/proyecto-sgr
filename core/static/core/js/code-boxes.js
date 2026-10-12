// Seis casillas para escribir el código de recuperación, una por dígito.
//
// El campo de texto del formulario (name="code") sigue siendo el que se envía y el que revisa validation.js:
// este script solo lo esconde y lo mantiene al día con lo que se escribe en las casillas. Así el servidor
// recibe lo mismo de siempre y, sin JavaScript, la persona ve el campo de texto normal.
//
// Se puede escribir, pegar el código completo (con espacios o sin ellos), borrar con retroceso y moverse con
// las flechas. Solo se aceptan dígitos.

(function () {
  "use strict";

  var source = document.querySelector("input[data-code-boxes]");
  if (!source) {
    return;
  }

  var length = parseInt(source.dataset.codeBoxes, 10) || 6;
  var label = source.id ? document.querySelector('label[for="' + source.id + '"]') : null;
  var title = label ? label.textContent.replace(/\(obligatorio\)|\*/g, "").trim() : "Código";

  var group = document.createElement("div");
  group.className = "code-boxes";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", title);
  if (source.id && document.getElementById(source.id + "_error")) {
    group.setAttribute("aria-describedby", source.id + "_error");
  }

  var boxes = [];
  for (var i = 0; i < length; i++) {
    var box = document.createElement("input");
    box.type = "text";
    box.className = "form-control code-box";
    box.setAttribute("inputmode", "numeric");
    box.setAttribute("autocomplete", "one-time-code");
    box.setAttribute("aria-label", "Dígito " + (i + 1) + " de " + length);
    box.setAttribute("autocapitalize", "off");
    box.spellcheck = false;
    group.appendChild(box);
    boxes.push(box);
  }

  function digitsOf(text) {
    return String(text || "").replace(/\D/g, "");
  }

  // Lo escrito en las casillas pasa al campo de verdad, y validation.js se entera como si se hubiera escrito en él.
  function sync() {
    source.value = boxes
      .map(function (box) {
        return box.value;
      })
      .join("");
    source.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Pone los dígitos desde la casilla start y deja el cursor en la siguiente a la última escrita.
  function fill(start, digits) {
    var index = start;
    for (var k = 0; k < digits.length && index < length; k++, index++) {
      boxes[index].value = digits.charAt(k);
    }
    boxes[Math.min(index, length - 1)].focus();
    sync();
  }

  // Dónde parte el cursor: la primera casilla vacía o, si están todas llenas, la última.
  function target() {
    for (var k = 0; k < length; k++) {
      if (boxes[k].value === "") {
        return boxes[k];
      }
    }
    return boxes[length - 1];
  }

  boxes.forEach(function (box, index) {
    // Al llegar a una casilla se selecciona su dígito: lo que se escriba lo reemplaza.
    box.addEventListener("focus", function () {
      box.select();
    });
    box.addEventListener("click", function () {
      box.select();
    });

    box.addEventListener("keydown", function (event) {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return; // copiar, pegar, etc.
      }
      var key = event.key;
      if (key === "Backspace" && box.value === "" && index > 0) {
        // En una casilla vacía, el retroceso borra el dígito anterior.
        event.preventDefault();
        boxes[index - 1].value = "";
        boxes[index - 1].focus();
        sync();
      } else if (key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        boxes[index - 1].focus();
      } else if (key === "ArrowRight" && index < length - 1) {
        event.preventDefault();
        boxes[index + 1].focus();
      } else if (key === "Home") {
        event.preventDefault();
        boxes[0].focus();
      } else if (key === "End") {
        event.preventDefault();
        boxes[length - 1].focus();
      } else if (key.length === 1 && !/\d/.test(key)) {
        event.preventDefault(); // letras y símbolos no entran
      } else if (/^\d$/.test(key) && box.value !== "") {
        box.select(); // el dígito nuevo reemplaza al que había
      }
    });

    // Escribir un dígito, o recibir varios de una vez (autocompletado del teléfono con el código del SMS).
    box.addEventListener("input", function () {
      var digits = digitsOf(box.value);
      if (digits === "") {
        box.value = "";
        sync();
        return;
      }
      box.value = digits.charAt(0);
      if (digits.length > 1) {
        fill(digits.length >= length ? 0 : index, digits);
      } else {
        fill(index, digits);
      }
    });

    // Pegar el código completo, aunque tenga espacios o guiones.
    box.addEventListener("paste", function (event) {
      var data = event.clipboardData || window.clipboardData;
      if (!data) {
        return;
      }
      event.preventDefault();
      var digits = digitsOf(data.getData("text"));
      if (digits !== "") {
        fill(digits.length >= length ? 0 : index, digits);
      }
    });
  });

  // Si el servidor devolvió el campo con un error, las casillas se marcan igual; validation.js cambia la clase del
  // campo y aquí se copia a las casillas.
  function mirrorErrors() {
    var invalid = source.classList.contains("is-invalid");
    group.classList.toggle("is-invalid", invalid);
    boxes.forEach(function (box) {
      if (invalid) {
        box.setAttribute("aria-invalid", "true");
      } else {
        box.removeAttribute("aria-invalid");
      }
    });
  }
  new MutationObserver(mirrorErrors).observe(source, { attributes: true, attributeFilter: ["class", "aria-invalid"] });

  // Se esconde el campo de texto (sigue en el formulario) y quien intente ponerle el cursor, por ejemplo al hacer
  // clic en la etiqueta o al revisar los errores, lo recibe en las casillas.
  source.classList.add("visually-hidden");
  source.setAttribute("tabindex", "-1");
  source.setAttribute("aria-hidden", "true");
  source.removeAttribute("autofocus");
  source.addEventListener("focus", function () {
    target().focus();
  });
  source.parentNode.insertBefore(group, source);

  // Lo que ya traía el campo (por ejemplo, el código que se escribió mal) se reparte entre las casillas.
  var previous = digitsOf(source.value).slice(0, length);
  for (var k = 0; k < previous.length; k++) {
    boxes[k].value = previous.charAt(k);
  }
  mirrorErrors();
  target().focus();
})();
