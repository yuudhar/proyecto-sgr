import ast
from pathlib import Path

HTTP = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "head": "HEAD"}


def _texto_ruta(nodo):
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(p.value if isinstance(p, ast.Constant) else "{…}" for p in nodo.values)
    if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", getattr(nodo.func, "attr", "")) in ("reverse", "reverse_lazy"):
        if nodo.args and isinstance(nodo.args[0], ast.Constant):
            return nodo.args[0].value
    if isinstance(nodo, ast.Name):
        return f"{nodo.id}"
    return "la ruta indicada en la prueba"


def _pasos_de_funcion(func, ayudas=None, profundidad=0):
    pasos = []
    for nodo in ast.walk(func):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        if isinstance(f, ast.Attribute):
            base = f.value
            if isinstance(base, ast.Name) and base.id == "self" and ayudas and profundidad < 2:
                ayuda = ayudas(f.attr)
                if ayuda is not None:
                    for texto in _pasos_de_funcion(ayuda, ayudas, profundidad + 1):
                        pasos.append((nodo.lineno, nodo.col_offset, texto))
                    continue
            primero = nodo.args[0] if nodo.args else None
            es_ruta = (
                isinstance(primero, ast.Call) and getattr(primero.func, "id", "") in ("reverse", "reverse_lazy")
            ) or (isinstance(primero, ast.Constant) and isinstance(primero.value, str) and primero.value.startswith("/"))
            es_cliente = (
                isinstance(base, ast.Attribute) and base.attr == "client"
                or isinstance(base, ast.Name) and base.id in ("client", "c")
                or es_ruta and f.attr in HTTP
            )
            if es_cliente and f.attr in HTTP and nodo.args:
                con_datos = " con los datos del formulario" if f.attr == "post" and len(nodo.args) > 1 else ""
                pasos.append((nodo.lineno, nodo.col_offset, f"{HTTP[f.attr]} {_texto_ruta(nodo.args[0])}{con_datos}"))
            elif es_cliente and f.attr == "force_login":
                pasos.append((nodo.lineno, nodo.col_offset, "Iniciar sesión con la cuenta de la prueba"))
            elif f.attr == "login_as" and nodo.args and isinstance(nodo.args[0], ast.Constant):
                pasos.append((nodo.lineno, nodo.col_offset, f"Iniciar sesión como «{nodo.args[0].value}»"))
            elif f.attr == "make_user" and nodo.args and isinstance(nodo.args[0], ast.Constant):
                pasos.append((nodo.lineno, nodo.col_offset, f"Crear el usuario «{nodo.args[0].value}»"))
        elif isinstance(f, ast.Name):
            if f.id == "call_command" and nodo.args and isinstance(nodo.args[0], ast.Constant):
                pasos.append((nodo.lineno, nodo.col_offset, f"Ejecutar el comando {nodo.args[0].value}"))
            elif f.id == "authenticate":
                pasos.append((nodo.lineno, nodo.col_offset, "Autenticar con las credenciales de la prueba"))
    pasos.sort(key=lambda p: (p[0], p[1]))
    return [texto for _, _, texto in pasos]


def _comprimir(pasos):
    salida = []
    for texto in pasos:
        if salida and salida[-1][0] == texto:
            salida[-1][1] += 1
        else:
            salida.append([texto, 1])
    pasos = [t if n == 1 else f"{t} (×{n})" for t, n in salida]
    if len(pasos) > 7:
        pasos = pasos[:7] + ["… (el resto de los pasos está en el código de la prueba)"]
    return pasos


class Indice:

    def __init__(self, base):
        self.base = Path(base)
        self.clases = {}
        archivos = sorted(self.base.glob("core/test_*.py")) + sorted(self.base.glob("accounts/test_*.py")) + [self.base / "core/tests.py"]
        for archivo in archivos:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for nodo in arbol.body:
                if isinstance(nodo, ast.ClassDef):
                    self.clases[nodo.name] = (archivo.relative_to(self.base).as_posix(), nodo)

    def archivo(self, clase):
        return self.clases[clase][0]

    def _set_up(self, clase, vistos=None):
        vistos = vistos or set()
        if clase in vistos or clase not in self.clases:
            return []
        vistos.add(clase)
        nodo = self.clases[clase][1]
        pasos = []
        for base in nodo.bases:
            nombre = getattr(base, "id", None)
            if nombre:
                pasos += self._set_up(nombre, vistos)
        for item in nodo.body:
            if isinstance(item, ast.FunctionDef) and item.name == "setUp":
                pasos += _pasos_de_funcion(item)
        return pasos

    def _buscar_ayuda(self, clase, nombre, vistos=None):
        vistos = vistos or set()
        if clase in vistos or clase not in self.clases:
            return None
        vistos.add(clase)
        nodo = self.clases[clase][1]
        for item in nodo.body:
            if isinstance(item, ast.FunctionDef) and item.name == nombre and not nombre.startswith(("test", "assert", "setUp")):
                return item
        for base in nodo.bases:
            encontrada = self._buscar_ayuda(getattr(base, "id", None), nombre, vistos)
            if encontrada is not None:
                return encontrada
        return None

    def pasos(self, clase, metodo):
        _, nodo = self.clases[clase]
        func = next(f for f in nodo.body if isinstance(f, ast.FunctionDef) and f.name == f"test_{metodo}")
        propios = _pasos_de_funcion(func, lambda nombre: self._buscar_ayuda(clase, nombre))
        previos = [p for p in self._set_up(clase) if p.startswith(("Iniciar sesión", "Crear el usuario"))]
        pasos = _comprimir(previos[:1] + propios) if (previos or propios) else []
        if not pasos:
            pasos = ["Preparar los datos de la prueba y llamar a la función que se prueba"]
        return pasos + ["Comprobar el resultado esperado"]
