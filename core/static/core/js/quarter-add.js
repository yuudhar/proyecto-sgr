// Agregar trimestre: muestra las fechas y los días de lunes a viernes del trimestre elegido, igual que el servidor.
const form = document.querySelector("[data-quarter-add]");

if (form) {
  const year = form.querySelector("#id_year");
  const quarter = form.querySelector("#id_quarter");
  const days = form.querySelector("#id_computable_days");
  const text = form.querySelector("[data-quarter-preview-text]");
  const LAST = { 1: [2, 31], 2: [5, 30], 3: [8, 30], 4: [11, 31] };

  const weekdays = (start, end) => {
    let total = 0;
    for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
      const weekday = day.getDay();
      if (weekday !== 0 && weekday !== 6) total += 1;
    }
    return total;
  };

  const format = (date) =>
    `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}/${date.getFullYear()}`;

  const refresh = () => {
    const y = parseInt(year.value, 10);
    const q = parseInt(quarter.value, 10);
    if (!y || !LAST[q]) {
      text.textContent = "Elige el año y el trimestre para ver las fechas.";
      return;
    }
    const start = new Date(y, (q - 1) * 3, 1);
    const end = new Date(y, LAST[q][0], LAST[q][1]);
    const count = weekdays(start, end);
    days.placeholder = `Se calcula solo: ${count}`;
    text.textContent = `Del ${format(start)} al ${format(end)}: ${count} días de lunes a viernes.`;
  };

  year.addEventListener("input", refresh);
  quarter.addEventListener("change", refresh);
  refresh();
}
