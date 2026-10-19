import Swal from "../vendor/sweetalert2/sweetalert2.esm.min.js";

export { Swal };

const keepFocus = (popup) => popup.addEventListener("focusin", (event) => event.stopPropagation());

export const alerta = Swal.mixin({
  confirmButtonText: "Entendido",
  cancelButtonText: "Cancelar",
  willOpen: keepFocus,
});

export const aviso = Swal.mixin({
  toast: true,
  position: "top-end",
  showConfirmButton: false,
  showCloseButton: true,
  timer: 4500,
  timerProgressBar: true,
  willOpen: keepFocus,
});
