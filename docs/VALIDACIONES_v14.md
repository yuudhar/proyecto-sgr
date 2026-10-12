# Validaciones de la v14

La v14 completa las validaciones de los formularios del portal sin tocar la base de datos (no hay migraciones nuevas). Todo se apoya en lo ya existente: `core/rules.py` (reglas de formato), `core/static/core/js/validation.js` (la misma regla en el navegador, con SweetAlert2) y `CrudForm.clean` (la misma regla en el servidor).

## Qué cambió

| Tema | Dónde |
|---|---|
| Política de contraseña | `accounts/validators.py` (validador), `sgr_project/settings.py` (5.º validador), regla `password` en `core/rules.py` y `validation.js`, ayuda en `password_help()` |
| Regla `text` para cuadros de varias líneas | `core/rules.py` y `validation.js` (normalizador `lines`) |
| Reglas de una línea para los campos que no tenían | `core/registry.py` (`rules` de cada mantenedor) |
| Largo máximo (`maxlength`) en todo campo de texto, 2000 en los cuadros de varias líneas | `CrudForm.set_text_limits` en `core/forms.py` |
| Rangos numéricos y fechas hacia el navegador (`min`, `max`, `data-not-before`) | `Crud.bounds` en `core/registry.py` y `CrudForm.apply_bounds` |
| Relaciones entre fechas y números en el servidor | `PositionForm`, `PositionItemForm`, `CommitmentForm`, `FollowupForm`, `ActivityEditForm`, `ActivityIntakeForm`, `GoalForm`, `PeriodForm` en `core/forms.py` |

## Contraseña

- De 8 a 128 caracteres, con minúscula, mayúscula, número y símbolo. Se mantienen similitud con los datos del usuario, uso común y solo números.
- El mensaje dice solo lo que falta («Le falta un número.»).
- `Hola123!` cumple; `admin12345` se rechaza.
- Se aplica a `password1` de *Control de usuarios*, `new_password1` de *Mi perfil* y de la recuperación.
- **Las cuentas existentes no se afectan:** `seed_demo_data`, `set_password` y `changepassword` no pasan por los formularios, así que no validan la política.

## Hallazgo extra: la meta no aceptaba el valor 0,01

`Goal.target_value` usa `MinValueValidator(0.01)` con un `float`, y `Decimal("0.01")` queda por debajo de ese float, así que el mínimo prometido se rechazaba (con un mensaje en inglés). Como cambiar el validador del modelo generaría una migración, se corrigió en `GoalForm` (el mínimo se revisa con `Decimal`). El modelo y la base quedan igual.

## Lo que NO se validó a propósito

- **Ingreso (login):** no se agregan reglas de formato para no revelar qué usuarios existen ni cómo se arma una contraseña.
- **Filtros de búsqueda (GET):** son consultas, no datos que se guarden.
- **`file_link` de evidencias:** es un nombre o ruta mostrado como texto, no un enlace que se abra; se valida como texto (`label`), sin exigir esquema `http`.
- **Fechas de seguimientos contra la actividad en el navegador:** el navegador no sabe qué actividad se eligió en la lista; esa comparación (seguimiento no anterior a la actividad) se hace solo en el servidor.
- **Informe ≤ beneficio:** solo se exige que ambas fechas no sean anteriores a la visita; no hay un orden entre informe y beneficio porque pueden ocurrir en cualquier orden.
- **Visita agendada (`scheduled_visit_date`):** puede ser futura (es una fecha planificada).
- **Compromisos vencidos:** se pueden registrar (se registran también los atrasados).
- **Fecha `max` en el navegador:** la calcula el servidor con la fecha de Chile, para que no dependa de la zona horaria del equipo de la persona.
- **Cuentas existentes frente a la política de contraseña:** ver arriba.
- **Largo de 2000 caracteres:** es un límite del formulario; la columna sigue siendo `TextField` sin tope.

## Cambios al diagrama

Ninguno. No hace falta agregar ni cambiar campos. Dos cosas que conviene saber, solo como aviso:

1. `Goal.target_value`: el validador del modelo compara con `float`; si algún día se hace una migración, conviene cambiarlo por `Decimal("0.01")`.
2. Si más adelante se quiere guardar *cuándo* cambió una persona su contraseña (para exigir cambio periódico), haría falta un campo nuevo en el perfil; no se agregó.

## Pruebas

Las pruebas nuevas están en `core/test_validaciones.py` (65 pruebas) y se registran en `core/qa/esperado_validaciones.py` y `core/qa/catalogo.py`. Se corrió la suite completa (`python manage.py test`, sin `--parallel`).
