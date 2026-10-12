// Ventanas de SweetAlert2 del sistema: una sola configuración, con los textos en español, que usan la
// validación de formularios, las confirmaciones, los avisos de resultado y los de error.

import Swal from "../vendor/sweetalert2/sweetalert2.esm.min.js";

export { Swal };

// Cuando hay una ventana modal de Bootstrap abierta, su trampa de foco le quita el foco a cualquier cosa
// que esté fuera de ella. Aquí se corta el aviso de foco antes de que llegue (willOpen corre antes de
// que la ventana tome el foco), para que sus botones se puedan usar con el teclado.
const keepFocus = (popup) => popup.addEventListener("focusin", (event) => event.stopPropagation());

export const alerta = Swal.mixin({
  confirmButtonText: "Entendido",
  cancelButtonText: "Cancelar",
  willOpen: keepFocus,
});

// Aviso corto que no tapa la pantalla (una cancelación, una confirmación de poca importancia).
export const aviso = Swal.mixin({
  toast: true,
  position: "top-end",
  showConfirmButton: false,
  showCloseButton: true,
  timer: 4500,
  timerProgressBar: true,
  willOpen: keepFocus,
});
