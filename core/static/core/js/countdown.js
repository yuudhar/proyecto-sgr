(function () {
  "use strict";

  function remaining(end) {
    return Math.max(0, Math.ceil((end - Date.now()) / 1000));
  }

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
      var resend = document.querySelector("[data-new-code]");
      if (resend) {
        resend.classList.remove("btn-outline-primary");
        resend.classList.add("btn-primary");
      }
    }

    clock.textContent = format(left);
    var timer = window.setInterval(tick, 1000);
  }

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
      if (status) {
        status.textContent = button.dataset.readyText || "";
      }
    }

    var timer = window.setInterval(tick, 1000);
  }

  codeClock();
  resendWait();
})();
