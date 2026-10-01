from django.shortcuts import render

def login_view(request):
    contexto = {
        "sistema": "SGR",
        "mensaje": "Sistema de Gestión de Resultados",
        "institucion": "Municipalidad de La Serena",
    }
    return render(request, "core/login.html", contexto)

def dashboard_view(request):
    funcionario = {
        "nombre": "Matías Cavieres",
        "cargo": "Encargado Territorial",
        "delegacion": "Centro",
    }
    metas = [
        {"item": "Atenciones comunitarias", "avance": 82, "meta": 100, "semaforo": "verde"},
        {"item": "Visitas domiciliarias", "avance": 45, "meta": 80, "semaforo": "ambar"},
        {"item": "Informes territoriales", "avance": 12, "meta": 30, "semaforo": "rojo"},
    ]
    return render(request, "core/dashboard.html", {
        "funcionario": funcionario,
        "metas": metas,
    })

def registrar_actividad_view(request):
    items = [
        {"id": 1, "nombre": "Atención social"},
        {"id": 2, "nombre": "Visita domiciliaria"},
        {"id": 3, "nombre": "Coordinación territorial"},
    ]
    return render(request, "core/registrar_actividad.html", {
        "items": items,
    })

def cargar_evidencia_view(request):
    actividad = {
        "id": 1,
        "fecha": "2026-09-14",
        "item": "Atención social",
    }
    return render(request, "core/cargar_evidencia.html", {
        "actividad": actividad,
    })

def validar_evidencia_view(request):
    evidencias_pendientes = [
        {"codigo": "EV-1-2026", "actividad": "Atención social", "funcionario": "Matías Cavieres", "fecha_carga": "2026-09-14"},
        {"codigo": "EV-2-2026", "actividad": "Visita domiciliaria", "funcionario": "Sakty Argandoña", "fecha_carga": "2026-09-13"},
    ]
    return render(request, "core/validar_evidencia.html", {
        "evidencias_pendientes": evidencias_pendientes,
    })

def agenda_colectiva_view(request):
    compromisos = [
        {"solicitante": "Junta de Vecinos Las Compañías", "territorio": "Las Compañías", "responsable": "Matías Cavieres", "fecha_comprometida": "2026-09-20", "estado": "Pendiente"},
        {"solicitante": "Comité de Adelanto La Antena", "territorio": "La Antena", "responsable": "Sakty Argandoña", "fecha_comprometida": "2026-09-18", "estado": "En proceso"},
        {"solicitante": "Vecino particular", "territorio": "Avenida del Mar", "responsable": "Matías Cavieres", "fecha_comprometida": "2026-09-10", "estado": "Realizado"},
    ]
    return render(request, "core/agenda_colectiva.html", {
        "compromisos": compromisos,
    })

def tablero_delegacion_view(request):
    delegacion = {"nombre": "Centro", "responsable": "Alan Von Kretschmann"}
    funcionarios = [
        {"nombre": "Matías Cavieres", "avance": 82, "meta_esperada": 75, "semaforo": "verde"},
        {"nombre": "Sakty Argandoña", "avance": 45, "meta_esperada": 60, "semaforo": "ambar"},
        {"nombre": "Matías Quiroz", "avance": 20, "meta_esperada": 55, "semaforo": "rojo"},
    ]
    resumen = {"promedio": 49, "total_funcionarios": 3}
    return render(request, "core/tablero_delegacion.html", {
        "delegacion": delegacion,
        "funcionarios": funcionarios,
        "resumen": resumen,
    })

def administracion_view(request):
    delegaciones = [
        {"nombre": "Centro", "estado": "Activa"},
        {"nombre": "Las Compañías", "estado": "Activa"},
        {"nombre": "La Pampa", "estado": "Activa"},
        {"nombre": "La Antena", "estado": "Activa"},
        {"nombre": "Avenida del Mar", "estado": "Activa"},
        {"nombre": "Rural", "estado": "Activa"},
    ]
    cargos = [
        {"nombre": "Encargado Territorial", "vigencia": "Vigente"},
        {"nombre": "Coordinador de Delegación", "vigencia": "Vigente"},
    ]
    periodo_actual = {"inicio": "2026-09-01", "termino": "2026-09-30", "estado": "En curso"}
    return render(request, "core/administracion.html", {
        "delegaciones": delegaciones,
        "cargos": cargos,
        "periodo_actual": periodo_actual,
    })

def informes_view(request):
    resumen_informe = [
        {"funcionario": "Matías Cavieres", "delegacion": "Centro", "actividades": 24, "cumplimiento": 82},
        {"funcionario": "Sakty Argandoña", "delegacion": "La Antena", "actividades": 15, "cumplimiento": 45},
        {"funcionario": "Matías Quiroz", "delegacion": "Avenida del Mar", "actividades": 8, "cumplimiento": 20},
    ]
    return render(request, "core/informes.html", {
        "resumen_informe": resumen_informe,
    })

def catalogo_servicios_view(request):
    servicios = [
        {"nombre": "Atención social", "estado": "Activo"},
        {"nombre": "Certificado de residencia", "estado": "Activo"},
        {"nombre": "Postulación a subsidio", "estado": "Activo"},
        {"nombre": "Reparación de alumbrado", "estado": "Inactivo"},
    ]
    return render(request, "core/catalogo_servicios.html", {
        "servicios": servicios,
    })
