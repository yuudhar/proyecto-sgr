# SGR · Programación Back End

Proyecto SGR (Sistema de Gestión de Resultados) hecho en Django para Programación Back End. La gestión se hace desde el Django Admin.

## Cómo correrlo en linux

Necesitas Python 3.12 o superior y Git. Usa SQLite, así que no hay que instalar ni configurar ninguna base de datos. Estos comandos son para Linux o macOS, los de Windows están más abajo.

```bash
git clone https://github.com/yuudhar/proyecto-sgr.git
cd proyecto-sgr

python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env

python manage.py check
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Después se entra a http://127.0.0.1:8000/admin/ con alguna de las cuentas de más abajo.

`seed_demo_data` es el que carga los roles, los datos de ejemplo y las cuentas de prueba, así que hay que correrlo antes de entrar. Las migraciones ya vienen en el repositorio, no hace falta `makemigrations`.

## Cómo correrlo en Windows

Instala Python 3.12 o superior (en el instalador marca «Add python.exe to PATH») y Git para Windows. Es lo mismo que arriba, cambian solo tres líneas: `python` en vez de `python3`, la activación del entorno virtual y el copiado del `.env`. Abre PowerShell y corre:

```powershell
git clone https://github.com/yuudhar/proyecto-sgr.git
cd proyecto-sgr

python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

copy .env.example .env

python manage.py check
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Después también se entra a http://127.0.0.1:8000/admin/ con las cuentas de más abajo.

Si `python` no se reconoce (o se abre la Microsoft Store), prueba con `py`, por ejemplo `py -m venv venv`. Si usas CMD en vez de PowerShell, el entorno se activa con `venv\Scripts\activate.bat`. Si PowerShell dice que la ejecución de scripts está deshabilitada, corre `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` y activa el entorno otra vez. Eso solo vale para esa ventana.

## Cuentas de prueba

Las crea `seed_demo_data`. Son solo para la demo, no son cuentas reales, y todas tienen la misma contraseña. En la demo se entra primero con `admin` y después con `matias.quiroz`, que es el usuario limitado y solo ve la Delegación Sur.

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `Hola123!` | Superusuario, ve todo (las dos delegaciones) |
| `matias.cavieres` | `Hola123!` | Funcionario y Verificador de la Delegación Norte, solo ve lo de Norte |
| `matias.quiroz` | `Hola123!` | Funcionario y Verificador de la Delegación Sur, solo ve lo de Sur |
| `coordinacion1` | `Hola123!` | Coordinación, sin funcionario asociado. Ve los catálogos, la planificación y los funcionarios y territorios de las dos delegaciones |
| `jefatura1` | `Hola123!` | Jefatura de la Delegación Norte, igual que un funcionario (solo ve Norte) |
