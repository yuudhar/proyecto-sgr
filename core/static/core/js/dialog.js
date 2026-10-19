const element = document.getElementById("sgr-modal");
const frame = element ? element.querySelector(".modal-dialog") : null;
const modal = element && window.bootstrap ? new window.bootstrap.Modal(element, { backdrop: "static", keyboard: false }) : null;

const below = [];
const closedListeners = [];
let visible = false;
let opener = null;

export const available = modal !== null;

function focusFirst(content) {
  const field = content.querySelector("[autofocus], input:not([type=hidden]):not([disabled]), select, textarea");
  (field || content).focus();
}

function place(content) {
  frame.replaceChildren(content);
}

export function open(content, returnTo = null) {
  if (!modal) return false;
  below.length = 0;
  place(content);
  if (visible) {
    focusFirst(content);
  } else {
    opener = returnTo || document.activeElement;
    modal.show();
  }
  return true;
}

export function push(content, returnTo = null) {
  if (!modal) return false;
  if (!visible) return open(content, returnTo);
  const current = frame.firstElementChild;
  const body = current.querySelector(".modal-body");
  below.push({ content: current, scroll: body ? body.scrollTop : 0, focus: document.activeElement });
  place(content);
  focusFirst(content);
  return true;
}

export function back() {
  const previous = below.pop();
  if (!previous) {
    close();
    return;
  }
  place(previous.content);
  const body = previous.content.querySelector(".modal-body");
  if (body) body.scrollTop = previous.scroll;
  if (previous.focus && previous.focus.isConnected) previous.focus.focus();
}

export function close() {
  if (modal && visible) modal.hide();
}

export function onClosed(listener) {
  closedListeners.push(listener);
}

if (element) {
  element.addEventListener("show.bs.modal", () => {
    visible = true;
  });
  element.addEventListener("shown.bs.modal", () => {
    if (frame.firstElementChild && !document.querySelector(".swal2-popup")) focusFirst(frame.firstElementChild);
  });
  element.addEventListener("hidden.bs.modal", () => {
    visible = false;
    frame.replaceChildren();
    below.length = 0;
    if (opener && opener.isConnected) opener.focus();
    opener = null;
    closedListeners.forEach((listener) => listener());
  });
  element.addEventListener("hidePrevented.bs.modal", (event) => event.preventDefault());
  element.addEventListener("click", (event) => {
    if (event.target.closest("[data-dialog-close]")) back();
  });
  element.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      back();
    }
  });
}
