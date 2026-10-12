// Pequeños ajustes de las pantallas. Todo sigue funcionando sin JavaScript.

(function () {
  "use strict";

  // Al enviar un formulario (data-once) el botón se desactiva y muestra un indicador de carga, para que un doble clic
  // no lo envíe dos veces: eso lo hace busy.js.

  // Si el formulario volvió con errores, el cursor parte en el primer campo con error.
  var firstInvalid = document.querySelector(".is-invalid");
  if (firstInvalid && typeof firstInvalid.focus === "function") {
    firstInvalid.focus({ preventScroll: false });
  }

  // Los avisos de Django los muestra flash.js con SweetAlert2 y, mientras tanto, la página los esconde (clase has-js).
  // Si flash.js no llegó a correr (no cargó, falló), se muestran como siempre para que ningún aviso se pierda.
  window.addEventListener("load", function () {
    if (!window.sgrFlashReady) {
      document.documentElement.classList.remove("has-js");
    }
  });

  // Los avisos de éxito e información se cierran solos; los de error y advertencia se quedan.
  document.querySelectorAll(".flash .alert-success, .flash .alert-info").forEach(function (alert) {
    window.setTimeout(function () {
      var close = alert.querySelector(".btn-close");
      if (close && document.body.contains(alert)) {
        close.click();
      }
    }, 8000);
  });

  // Botón "Imprimir" de los informes.
  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });
})();
