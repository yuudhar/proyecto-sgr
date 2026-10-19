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

  function sync() {
    source.value = boxes
      .map(function (box) {
        return box.value;
      })
      .join("");
    source.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function fill(start, digits) {
    var index = start;
    for (var k = 0; k < digits.length && index < length; k++, index++) {
      boxes[index].value = digits.charAt(k);
    }
    boxes[Math.min(index, length - 1)].focus();
    sync();
  }

  function target() {
    for (var k = 0; k < length; k++) {
      if (boxes[k].value === "") {
        return boxes[k];
      }
    }
    return boxes[length - 1];
  }

  boxes.forEach(function (box, index) {
    box.addEventListener("focus", function () {
      box.select();
    });
    box.addEventListener("click", function () {
      box.select();
    });

    box.addEventListener("keydown", function (event) {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      var key = event.key;
      if (key === "Backspace" && box.value === "" && index > 0) {
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
        event.preventDefault();
      } else if (/^\d$/.test(key) && box.value !== "") {
        box.select();
      }
    });

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

  source.classList.add("visually-hidden");
  source.setAttribute("tabindex", "-1");
  source.setAttribute("aria-hidden", "true");
  source.removeAttribute("autofocus");
  source.addEventListener("focus", function () {
    target().focus();
  });
  source.parentNode.insertBefore(group, source);

  var previous = digitsOf(source.value).slice(0, length);
  for (var k = 0; k < previous.length; k++) {
    boxes[k].value = previous.charAt(k);
  }
  mirrorErrors();
  target().focus();
})();
