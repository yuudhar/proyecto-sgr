// Avisa a las hojas de estilo que hay JavaScript. Va en el <head> para que se aplique antes de dibujar la página:
// así los avisos de Django, que flash.js muestra como ventanas de SweetAlert2, no parpadean arriba de la página.
// Sin JavaScript esta marca no existe y los avisos se ven como siempre.
document.documentElement.classList.add("has-js");
