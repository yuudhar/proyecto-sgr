(function () {
  "use strict";

  var firstInvalid = document.querySelector(".is-invalid");
  if (firstInvalid && typeof firstInvalid.focus === "function") {
    firstInvalid.focus({ preventScroll: false });
  }

  window.addEventListener("load", function () {
    if (!window.sgrFlashReady) {
      document.documentElement.classList.remove("has-js");
    }
  });

  document.querySelectorAll(".flash .alert-success, .flash .alert-info").forEach(function (alert) {
    window.setTimeout(function () {
      var close = alert.querySelector(".btn-close");
      if (close && document.body.contains(alert)) {
        close.click();
      }
    }, 8000);
  });

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });
})();
