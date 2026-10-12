// Relojes de la pantalla donde se escribe el código de recuperación.
//
//  1. Cuánto le queda al código (data-countdown).
//  2. Cuánto falta para poder reenviarlo (data-resend): el botón queda desactivado mientras corre la espera.
//
// Solo avisan cuánto falta: quien decide es el servidor (accounts/recovery.py), que revisa el vencimiento
// del código y la espera del reenvío con su propia hora. Sin JavaScript la pantalla funciona igual; se ve el
// tiempo que quedaba al cargar la página y, si se aprieta "Reenviar" antes de tiempo, el servidor avisa cuánto falta.

(function () {
  "use strict";

  // Los dos relojes se cuentan contra la hora del navegador y no sumando de a uno, para que no se atrasen
  // si la pestaña queda en segundo plano.
  function remaining(end) {
    return Math.max(0, Math.ceil((end - Date.now()) / 1000));
  }

  // -- 1. Vigencia del código ---------------------------------------------------------------

  function codeClock() {
    var box = document.querySelector("[data-countdown]");
    if (!box) {
      return;
    }
    var clock = box.querySelector("[data-countdown-clock]");
    var text = box.querySelector("[data-countdown-text]");
    var status = box.querySelector("[data-countdown-status]");
    var left = parseInt(box.dataset.seconds, 10) || 0;
    if (left <= 0 || !clock) {
      return;
    }
    var end = Date.now() + left * 1000;

    function format(seconds) {
      return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
    }

    function tick() {
      var seconds = remaining(end);
      clock.textContent = format(seconds);
      if (seconds > 0) {
        return;
      }
      window.clearInterval(timer);
      box.classList.add("is-over");
      text.textContent = box.dataset.overText;
      if (status) {
        status.textContent = box.dataset.overText;
      }
      // El código ya no sirve: el botón para pedir otro pasa a ser el principal.
      var resend = document.querySelector("[data-new-code]");
      if (resend) {
        resend.classList.remove("btn-outline-primary");
        resend.classList.add("btn-primary");
      }
    }

    clock.textContent = format(left);
    var timer = window.setInterval(tick, 1000);
  }

  // -- 2. Espera para reenviar --------------------------------------------------------------

  function resendWait() {
    var button = document.querySelector("[data-resend]");
    if (!button) {
      return;
    }
    var left = parseInt(button.dataset.seconds, 10) || 0;
    var text = button.querySelector("[data-resend-text]");
    var status = document.querySelector("[data-resend-status]");
    if (left <= 0 || !text) {
      return;
    }
    var label = "Reenviar código";
    var end = Date.now() + left * 1000;
    button.disabled = true;

    function tick() {
      var seconds = remaining(end);
      if (seconds > 0) {
        text.textContent = label + " (en " + seconds + " s)";
        return;
      }
      window.clearInterval(timer);
      text.textContent = label;
      button.disabled = false;
      // Se avisa una sola vez, cuando ya se puede (no cada segundo, para no llenar de avisos a un lector de pantalla).
      if (status) {
        status.textContent = button.dataset.readyText || "";
      }
    }

    var timer = window.setInterval(tick, 1000);
  }

  codeClock();
  resendWait();
})();
