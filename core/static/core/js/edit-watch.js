// Aviso mientras se edita: si otra persona guarda el mismo registro con el formulario abierto, aparece un
// aviso arriba del formulario. No cambia lo que la persona escribió ni recarga nada: al guardar, el servidor
// sigue comparando la versión y pide revisar los datos (RF-034, RNF-003).
//
// El aviso por WebSocket no lleva datos: al recibirlo, el formulario pregunta por HTTP si su registro cambió
// (el servidor aplica permisos y delegación). Sin WebSocket, el formulario pregunta cada cierto tiempo.
const scheme = location.protocol === "https:" ? "wss" : "ws";
const MAX_RETRIES = 5;
const POLL_MS = 20000;
const watched = new WeakSet();

function banner(text) {
  const box = document.createElement("div");
  box.className = "alert alert-warning d-flex gap-2";
  box.setAttribute("role", "alert");
  box.dataset.editWatch = "";
  const icon = document.createElement("i");
  icon.className = "bi bi-exclamation-triangle-fill";
  icon.setAttribute("aria-hidden", "true");
  const body = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "Cambió mientras editabas. ";
  const message = document.createElement("span");
  message.dataset.editWatchText = "";
  message.textContent = text;
  body.append(title, message);
  box.append(icon, body);
  return box;
}

function show(form, text, gone) {
  let box = form.querySelector("[data-edit-watch]");
  if (!box) {
    box = banner(text);
    const host = form.querySelector(".modal-body, .panel-body") || form;
    host.prepend(box);
  } else {
    box.querySelector("[data-edit-watch-text]").textContent = text;
  }
  box.classList.toggle("alert-danger", Boolean(gone));
  box.classList.toggle("alert-warning", !gone);
}

function watch(form) {
  if (watched.has(form)) return;
  watched.add(form);
  const slug = form.dataset.watchSlug;
  const url = form.dataset.watchUrl;
  let socket = null;
  let timer = null;
  let poller = null;
  let attempts = 0;
  let closed = false;
  let ticket = 0;

  function stop() {
    closed = true;
    window.clearTimeout(timer);
    window.clearTimeout(poller);
    if (socket) socket.close();
  }

  async function check() {
    if (closed) return;
    if (!form.isConnected) return stop();
    const version = form.querySelector('input[name="_version"]');
    if (!version) return;
    const mine = ++ticket;
    try {
      const response = await fetch(`${url}?abierta=${encodeURIComponent(version.value)}`, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });
      if (mine !== ticket || !response.ok) return;
      const result = await response.json();
      if (result.stale) show(form, result.message, result.gone);
    } catch (error) {
      console.error("No se pudo revisar si el registro cambió", error);
    }
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(check, 400); // varios avisos seguidos → una sola consulta
  }

  function poll() {
    window.clearTimeout(poller);
    poller = window.setTimeout(() => {
      if (closed) return;
      if (!form.isConnected) return stop();
      if (!document.hidden) check();
      poll();
    }, POLL_MS);
  }

  function open() {
    if (closed) return;
    socket = new WebSocket(`${scheme}://${location.host}/ws/crud/${encodeURIComponent(slug)}/`);
    let opened = false;
    socket.onopen = () => {
      opened = true;
      attempts = 0;
    };
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "crud_changed" && data.slug === slug) schedule();
    };
    socket.onclose = () => {
      if (closed || !form.isConnected) return stop();
      if (!opened && attempts >= MAX_RETRIES) return; // sin WebSocket queda la consulta periódica
      attempts += 1;
      window.setTimeout(open, Math.min(30000, 1000 * 2 ** attempts));
    };
    socket.onerror = () => socket.close();
  }

  open();
  poll();
}

function scan(root) {
  if (root.matches?.("form[data-watch-url]")) watch(root);
  root.querySelectorAll?.("form[data-watch-url]").forEach(watch);
}

scan(document);
new MutationObserver((records) => {
  records.forEach((record) => record.addedNodes.forEach((node) => node.nodeType === 1 && scan(node)));
}).observe(document.body, { childList: true, subtree: true });
