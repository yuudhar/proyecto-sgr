const DELAY_MS = 350;
const TEXT_FIELDS = "input[type=search], input[type=text]";

function setup(form) {
  let timer = null;
  let controller = null;
  let ticket = 0;
  let last = serialize(form);

  function serialize(source) {
    const params = new URLSearchParams(new FormData(source));
    params.delete("formato");
    return params.toString();
  }

  function announce() {
    const status = form.querySelector("[data-live-status]");
    const block = document.querySelector("[data-live-count]");
    if (!status || !block) return;
    const count = Number(block.getAttribute("data-live-count"));
    status.textContent = count === 1 ? "1 resultado" : `${count} resultados`;
  }

  async function run() {
    timer = null;
    const query = serialize(form);
    if (query === last) return;
    last = query;
    if (controller) controller.abort();
    controller = new AbortController();
    const mine = ++ticket;
    const base = form.getAttribute("action") || window.location.pathname;
    const url = query ? `${base}?${query}` : base;
    const targets = [...document.querySelectorAll("[data-live-target]")];
    targets.forEach((target) => target.setAttribute("aria-busy", "true"));
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
        signal: controller.signal,
      });
      if (mine !== ticket) return;
      const final = new URL(response.url, window.location.href);
      if (final.pathname !== new URL(base, window.location.href).pathname) {
        window.location.href = response.url;
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
      targets.forEach((target) => {
        const key = target.getAttribute("data-live-target");
        const next = fresh.querySelector(`[data-live-target="${key}"]`);
        if (next) target.replaceWith(next);
      });
      const button = form.querySelector("button[name=formato]");
      const freshButton = fresh.querySelector("form[data-live-search] button[name=formato]");
      if (button && freshButton) button.disabled = freshButton.disabled;
      window.history.replaceState(null, "", url);
      announce();
    } catch (error) {
      if (error.name === "AbortError") return;
      last = "";
      targets.forEach((target) => target.removeAttribute("aria-busy"));
    }
  }

  function schedule(delay) {
    window.clearTimeout(timer);
    timer = window.setTimeout(run, delay);
  }

  form.addEventListener("input", (event) => {
    if (event.target instanceof Element && event.target.matches(TEXT_FIELDS)) schedule(DELAY_MS);
  });
  form.addEventListener("change", (event) => {
    if (event.target instanceof Element && event.target.matches("select")) schedule(0);
  });
  form.addEventListener("submit", () => {
    window.clearTimeout(timer);
    if (controller) controller.abort();
    ticket += 1;
  });
}

document.querySelectorAll("form[data-live-search]").forEach(setup);
