// Recorte de la foto de perfil con Croppr (librería en core/static/core/vendor/croppr/).
//
// Flujo: la persona elige una imagen → se abre Croppr con una selección cuadrada → una vista previa muestra
// cómo quedará → «Guardar foto» recorta la imagen real (no con CSS) en un canvas, deja ese recorte en el campo
// de archivo y envía el formulario. «Cancelar» descarta todo: no se envía nada y la foto anterior sigue igual.
//
// Sin JavaScript o sin la librería, el formulario funciona como una subida normal y el servidor centra y recorta
// la imagen a un cuadrado. El servidor valida siempre la imagen que llega y la asocia a quien tiene la sesión.

const OUTPUT_PX = 512;
const PREVIEW_PX = 160;
const SOURCE_TYPES = ["image/png", "image/jpeg"];

function setUp(form) {
  const Croppr = window.Croppr;
  if (typeof Croppr !== "function") return;
  const input = form.querySelector('input[type="file"]');
  const panel = form.querySelector("[data-crop-panel]");
  const image = form.querySelector("[data-crop-image]");
  const preview = form.querySelector("[data-crop-preview]");
  const save = form.querySelector("[data-crop-save]");
  const cancel = form.querySelector("[data-crop-cancel]");
  const message = form.querySelector("[data-crop-message]");
  const normal = form.querySelectorAll("[data-crop-normal]");
  if (!input || !panel || !image || !preview || !save || !cancel) return;

  const maxSourceMb = Number(form.dataset.cropMaxSourceMb || 15);
  const maxMb = Number(input.dataset.maxMb || 2);
  let cropper = null;
  let source = null;
  let objectUrl = "";
  let original = null;

  const say = (text) => {
    if (message) {
      message.textContent = text;
      message.hidden = !text;
    }
  };

  function close() {
    if (cropper) {
      cropper.destroy();
      cropper = null;
    }
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    source = null;
    original = null;
    input.removeAttribute("data-crop-pending");
    input.value = "";
    image.removeAttribute("src");
    panel.hidden = true;
    normal.forEach((part) => (part.hidden = false));
    save.disabled = false;
  }

  function drawPreview(value) {
    if (!source) return;
    const crop = value || cropper.getValue();
    const context = preview.getContext("2d");
    context.clearRect(0, 0, preview.width, preview.height);
    context.drawImage(source, crop.x, crop.y, crop.width, crop.height, 0, 0, preview.width, preview.height);
  }

  function open(file) {
    if (!SOURCE_TYPES.includes(file.type)) {
      input.value = "";
      say("Esa imagen no se acepta. Elige un archivo PNG o JPG.");
      return;
    }
    if (file.size > maxSourceMb * 1024 * 1024) {
      input.value = "";
      say(`La imagen pesa más de ${maxSourceMb} MB. Elige una más liviana.`);
      return;
    }
    say("");
    original = file;
    input.setAttribute("data-crop-pending", "");
    objectUrl = URL.createObjectURL(file);
    const loaded = new Image();
    loaded.onload = () => {
      source = loaded;
      panel.hidden = false;
      normal.forEach((part) => (part.hidden = true));
      image.onload = () => {
        if (cropper) cropper.destroy();
        cropper = new Croppr(image, {
          aspectRatio: 1,
          startSize: [80, 80, "%"],
          minSize: [15, 15, "%"],
          returnMode: "real",
          onInitialize: (instance) => drawPreview(instance.getValue()),
          onCropMove: drawPreview,
          onCropEnd: drawPreview,
        });
      };
      image.src = objectUrl;
    };
    loaded.onerror = () => {
      close();
      say("No se pudo leer la imagen. Revisa que no esté dañada.");
    };
    loaded.src = objectUrl;
  }

  function encode(canvas, type, quality) {
    return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
  }

  async function finish() {
    if (!cropper || !source) return;
    save.disabled = true;
    const crop = cropper.getValue();
    const side = Math.max(1, Math.min(OUTPUT_PX, Math.round(Math.min(crop.width, crop.height))));
    const canvas = document.createElement("canvas");
    canvas.width = side;
    canvas.height = side;
    canvas.getContext("2d").drawImage(source, crop.x, crop.y, crop.width, crop.height, 0, 0, side, side);

    const png = original.type === "image/png";
    const type = png ? "image/png" : "image/jpeg";
    let blob = await encode(canvas, type, 0.92);
    for (const quality of [0.8, 0.65]) {
      if (blob && blob.size <= maxMb * 1024 * 1024) break;
      if (!png) blob = await encode(canvas, type, quality);
    }
    if (!blob || blob.size > maxMb * 1024 * 1024) {
      say(`El recorte pesa más de ${maxMb} MB. Elige un recorte más pequeño u otra imagen.`);
      save.disabled = false;
      return;
    }
    const stem = original.name.replace(/\.[^.]+$/, "") || "foto";
    const file = new File([blob], `${stem}.${png ? "png" : "jpg"}`, { type });
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    } catch (error) {
      say("Este navegador no permite enviar el recorte. Cancela y sube la imagen sin recortar.");
      save.disabled = false;
      return;
    }
    input.removeAttribute("data-crop-pending");
    form.requestSubmit();
  }

  function replacement(file) {
    const transfer = new DataTransfer();
    if (file) transfer.items.add(file);
    return transfer.files;
  }

  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (cropper) {
      close();
      input.files = replacement(file);
    }
    if (file) open(file);
  });
  save.addEventListener("click", finish);
  cancel.addEventListener("click", () => {
    close();
    say("");
  });
}

document.querySelectorAll("form[data-photo-crop]").forEach(setUp);
