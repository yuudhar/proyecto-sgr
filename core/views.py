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
