// Pantallas en vivo (Clase 11 aplicada al sistema): cuando otra persona cambia un dato, el servidor avisa
// por WebSocket y este script vuelve a pedir por HTTP la misma pantalla. No recibe datos por el socket:
// la pantalla vuelve a aplicar permisos, delegación, filtros y paginación antes de responder.
//
// Hay dos modos, según el marcador que tenga la página:
//   [data-live-crud="<slug>"]  listado de un mantenedor  →  /ws/crud/<slug>/  →  [data-live-target="resultados"]
//   [data-live-page]           dashboard, tablero y validar →  /ws/live/        →  [data-live-region]
import { aviso } from "./alerts.js";

const scheme = location.protocol === "https:" ? "wss" : "ws";
const MAX_RETRIES = 5;

function startLive({ path, accepts, selector, message }) {
  let attempts = 0;
  let refreshTimer = null;
  let ticket = 0;
  let current = { text: "Conectando…", tone: "neutral" };

  function setState(text, tone) {
    current = { text, tone };
    const el = document.querySelector("[data-live-state]");
    if (!el) return;
    el.hidden = false;
    el.className = "chip chip-" + tone;
    el.querySelector("[data-live-text]").textContent = text;
  }

  async function refresh() {
    const mine = ++ticket;
    try {
      const response = await fetch(location.href, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });
      if (mine !== ticket) return;
      if (!response.ok || new URL(response.url).pathname !== location.pathname) return;
      const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
      const region = document.querySelector(selector);
      const next = fresh.querySelector(selector);
      if (!region || !next) return;
      region.replaceWith(next);
      setState(current.text, current.tone); // la región nueva trae el indicador oculto: se vuelve a mostrar
      const status = document.querySelector("[data-live-status]");
      if (status) status.textContent = message.status;
      aviso.fire({ icon: "info", title: message.title, text: "Otra persona hizo un cambio.", timer: 2500 });
    } catch (error) {
      console.error("No se pudo actualizar la pantalla", error);
    }
  }

  function schedule() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refresh, 300); // varios avisos seguidos → una sola actualización
  }

  function connect() {
    const socket = new WebSocket(`${scheme}://${location.host}${path}`);
    let opened = false;
    socket.onopen = () => {
      opened = true;
      attempts = 0;
      setState("En vivo", "ok");
    };
    socket.onmessage = (event) => {
      if (accepts(JSON.parse(event.data))) schedule();
    };
    socket.onclose = () => {
      if (!opened && attempts >= MAX_RETRIES) {
        setState("Sin actualización en vivo", "neutral");
        return;
      }
      setState("Reconectando…", "warn");
      attempts += 1;
      window.setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts));
    };
    socket.onerror = () => socket.close();
  }

  connect();
}

const panel = document.querySelector("[data-live-crud]");
if (panel) {
  const slug = panel.dataset.liveCrud;
  startLive({
    path: `/ws/crud/${encodeURIComponent(slug)}/`,
    accepts: (data) => data.type === "crud_changed" && data.slug === slug,
    selector: '[data-live-target="resultados"]',
    message: { title: "Listado actualizado", status: "El listado se actualizó." },
  });
} else if (document.querySelector("[data-live-page]")) {
  startLive({
    path: "/ws/live/",
    accepts: (data) => data.type === "live_changed",
    selector: "[data-live-region]",
    message: { title: "Pantalla actualizada", status: "La pantalla se actualizó." },
  });
}
