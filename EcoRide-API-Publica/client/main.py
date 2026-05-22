"""
╔══════════════════════════════════════════════════════════╗
║        EcoRide — Cliente CLI                             ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sys
import requests

# ================================================================
#  CONFIGURACIÓN
# ================================================================
API_URL = os.environ.get("ECORIDE_API", "http://localhost:5000").rstrip("/")

# Estado de sesión (en memoria, se pierde al cerrar el programa)
SESSION = {
    "token"   : None,   # JWT
    "role"    : None,   # "user" o "admin"
    "username": None,
}


# ================================================================
#  COLORES (funciona en Windows 10+ / Linux / Mac)
# ================================================================
def _c(code): return f"\033[{code}m"

RESET  = _c(0)
BOLD   = _c(1)
RED    = _c(91)
GREEN  = _c(92)
YELLOW = _c(93)
CYAN   = _c(96)
WHITE  = _c(97)


# ================================================================
#  UTILIDADES DE PANTALLA
# ================================================================
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def line(char="─", width=58):
    print(f"{CYAN}{char * width}{RESET}")

def header(title: str):
    clear_screen()
    line("═")
    print(f"{CYAN}{BOLD}   🛴  EcoRide  —  {title}{RESET}")
    line("═")

def print_ok(msg: str):
    print(f"\n  {GREEN}✔  {msg}{RESET}")

def print_err(msg: str):
    print(f"\n  {RED}✘  {msg}{RESET}")

def print_info(msg: str):
    print(f"\n  {YELLOW}ℹ  {msg}{RESET}")

def press_enter():
    input(f"\n  {YELLOW}[ Pulsa ENTER para continuar ]{RESET}")


# ================================================================
#  CAPA DE RED  —  todas las llamadas HTTP pasan por aquí
# ================================================================
def _auth_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if SESSION["token"]:
        h["Authorization"] = f"Bearer {SESSION['token']}"
    return h

def _call(method: str, endpoint: str, body: dict = None, params: dict = None):
    """
    Realiza la petición HTTP y devuelve (status_code, data_dict).
    Si hay error de red devuelve (0, None).
    Nunca lanza excepciones al código que llama.
    """
    url = f"{API_URL}{endpoint}"
    try:
        resp = requests.request(
            method,
            url,
            json=body,
            params=params,
            headers=_auth_headers(),
            timeout=8,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"error": f"Respuesta no-JSON (código {resp.status_code})"}
        return resp.status_code, data

    except requests.exceptions.ConnectionError:
        return 0, None
    except requests.exceptions.Timeout:
        return 0, None


def handle(status: int, data: dict, ok_codes=(200, 201)) -> dict | None:
    """
    Muestra mensaje de éxito o error y devuelve el dict si fue éxito, None si no.
    """
    if status == 0 or data is None:
        print_err("No se pudo conectar al servidor. ¿Está en marcha?")
        return None

    if status in ok_codes:
        msg = data.get("message")
        if msg:
            print_ok(msg)
        return data

    # Error de la API
    msg = data.get("error") or data.get("message") or f"Error HTTP {status}"
    print_err(msg)
    return None


# ================================================================
#  PANTALLAS DE AUTENTICACIÓN
# ================================================================
def screen_login():
    header("Iniciar Sesión")
    email    = input(f"\n  {WHITE}Email    : {RESET}").strip()
    password = input(f"  {WHITE}Password : {RESET}").strip()

    status, data = _call("POST", "/auth/login", {"email": email, "password": password})
    result = handle(status, data)
    if result:
        SESSION["token"]    = result["access_token"]
        SESSION["role"]     = result["role"]
        SESSION["username"] = result["username"]
        print_ok(f"Bienvenido/a, {result['username']}  [{result['role'].upper()}]")
    press_enter()


def screen_register():
    header("Crear Cuenta Nueva")
    username = input(f"\n  {WHITE}Nombre de usuario : {RESET}").strip()
    email    = input(f"  {WHITE}Email             : {RESET}").strip()
    password = input(f"  {WHITE}Contraseña        : {RESET}").strip()

    status, data = _call("POST", "/auth/register", {
        "username": username,
        "email"   : email,
        "password": password,
    })
    if handle(status, data, ok_codes=(201,)):
        print_info("Ahora puedes iniciar sesión con tus nuevas credenciales.")
    press_enter()


def do_logout():
    SESSION["token"]    = None
    SESSION["role"]     = None
    SESSION["username"] = None
    print_ok("Sesión cerrada. ¡Hasta pronto!")
    press_enter()


# ================================================================
#  FUNCIONES USUARIO ESTÁNDAR
# ================================================================
def user_ver_patinetes():
    header("Patinetes Disponibles")
    status, data = _call("GET", "/vehicles")
    result = handle(status, data)
    if not result:
        press_enter(); return

    vehicles = result.get("vehicles", [])
    if not vehicles:
        print_info("No hay patinetes disponibles ahora mismo.")
    else:
        print(f"\n  {BOLD}{'#':<4} {'ID':<26} {'Modelo':<22} {'Bat':>4}  {'€/min':>6}  Ubicación{RESET}")
        line()
        for i, v in enumerate(vehicles, 1):
            print(f"  {i:<4} {v['_id']:<26} {v['model']:<22} {v['battery']:>3}%  {v['price_per_min']:>5.2f}€  {v.get('location','')}")
    press_enter()


def user_alquilar():
    header("Alquilar Patinete")

    # Mostrar disponibles para que el usuario elija
    status, data = _call("GET", "/vehicles")
    result = handle(status, data)
    if not result:
        press_enter(); return

    vehicles = result.get("vehicles", [])
    if not vehicles:
        print_info("No hay patinetes disponibles.")
        press_enter(); return

    print(f"\n  {BOLD}{'N°':<4} {'Modelo':<22} {'Bat':>4}  {'€/min':>6}  Ubicación{RESET}")
    line()
    for i, v in enumerate(vehicles, 1):
        print(f"  {i:<4} {v['model']:<22} {v['battery']:>3}%  {v['price_per_min']:>5.2f}€  {v.get('location','')}")

    choice = input(f"\n  Número del patinete (0=cancelar): ").strip()
    if choice == "0":
        return
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(vehicles)):
            raise ValueError
        vehicle_id = vehicles[idx]["_id"]
    except (ValueError, IndexError):
        print_err("Selección inválida."); press_enter(); return

    status, data = _call("POST", "/rentals/start", {"vehicle_id": vehicle_id})
    r = handle(status, data, ok_codes=(201,))
    if r:
        print(f"\n  {CYAN}Rental ID: {r.get('rental_id')}{RESET}")
    press_enter()


def user_finalizar_alquiler():
    header("Finalizar Alquiler Activo")

    status, data = _call("GET", "/rentals/active")
    result = handle(status, data)
    if not result:
        press_enter(); return

    rental = result.get("rental")
    if not rental:
        print_info(result.get("message", "No tienes alquiler activo."))
        press_enter(); return

    print(f"\n  Patinete : {CYAN}{rental.get('vehicle_model')}{RESET}")
    print(f"  Iniciado : {rental.get('start_time')}")
    print(f"  Tarifa   : {rental.get('price_per_min')} €/min")

    confirm = input(f"\n  ¿Finalizar este alquiler? {YELLOW}[s/N]{RESET}: ").strip().lower()
    if confirm != "s":
        print_info("Operación cancelada."); press_enter(); return

    status2, data2 = _call("PUT", f"/rentals/end/{rental['_id']}")
    r = handle(status2, data2)
    if r:
        print(f"\n  {BOLD}⏱  Duración : {r.get('duration_min')} minutos{RESET}")
        print(f"  {BOLD}💶 Total    : {r.get('total_cost')} €{RESET}")
    press_enter()


def user_historial():
    header("Mi Historial de Alquileres")
    status, data = _call("GET", "/rentals/my-history")
    result = handle(status, data)
    if not result:
        press_enter(); return

    rentals = result.get("rentals", [])
    if not rentals:
        print_info("Todavía no tienes alquileres registrados.")
    else:
        for r in rentals:
            estado = r.get("status", "").upper()
            color  = GREEN if estado == "FINALIZADO" else YELLOW
            print(f"\n  {color}[{estado}]{RESET}  {r.get('vehicle_model','')}")
            print(f"    Inicio  : {r.get('start_time', '—')}")
            print(f"    Fin     : {r.get('end_time') or 'En curso'}")
            coste = r.get('total_cost')
            print(f"    Coste   : {f'{coste} €' if coste else '—'}  ({r.get('duration_min','—')} min)")
    press_enter()


def user_mi_perfil():
    header("Mi Perfil")
    status, data = _call("GET", "/users/me")
    result = handle(status, data)
    if not result:
        press_enter(); return
    u = result.get("user", {})
    print(f"\n  Usuario   : {CYAN}{u.get('username')}{RESET}")
    print(f"  Email     : {u.get('email')}")
    print(f"  Rol       : {u.get('role','').upper()}")
    print(f"  Estado    : {'Activo' if u.get('active') else 'Desactivado'}")
    print(f"  Registro  : {u.get('created_at','—')}")
    press_enter()


# ================================================================
#  FUNCIONES ADMIN
# ================================================================
def admin_ver_vehiculos():
    header("Todos los Vehículos")
    filtro = input(f"  Filtrar estado (disponible/en_uso/mantenimiento, ENTER=todos): ").strip() or None
    params = {"status": filtro} if filtro else None
    status, data = _call("GET", "/vehicles", params=params)
    result = handle(status, data)
    if not result:
        press_enter(); return

    vehicles = result.get("vehicles", [])
    COLORS = {"disponible": GREEN, "en_uso": YELLOW, "mantenimiento": RED}
    if not vehicles:
        print_info("No se encontraron vehículos.")
    else:
        print(f"\n  {BOLD}{'ID':<26} {'Modelo':<22} {'Bat':>4}  {'Estado':<15} {'€/min':>6}  Ubicación{RESET}")
        line()
        for v in vehicles:
            c = COLORS.get(v.get("status",""), RESET)
            print(f"  {v['_id']:<26} {v['model']:<22} {v['battery']:>3}%  {c}{v['status']:<15}{RESET} {v['price_per_min']:>5.2f}€  {v.get('location','')}")
    press_enter()


def admin_crear_vehiculo():
    header("Crear Nuevo Patinete")
    model    = input(f"  Modelo        : ").strip()
    battery  = input(f"  Batería (0-100): ").strip()
    location = input(f"  Ubicación     : ").strip()
    price    = input(f"  Precio €/min  : ").strip()

    try:
        battery = int(battery)
        price   = float(price)
    except ValueError:
        print_err("Batería debe ser número entero y precio número decimal."); press_enter(); return

    status, data = _call("POST", "/vehicles", {
        "model"        : model,
        "battery"      : battery,
        "location"     : location,
        "price_per_min": price,
    })
    r = handle(status, data, ok_codes=(201,))
    if r:
        print(f"  {CYAN}ID del nuevo patinete: {r.get('vehicle_id')}{RESET}")
    press_enter()


def admin_editar_vehiculo():
    header("Editar Patinete")
    vid = input("  ID del patinete: ").strip()

    # Mostrar datos actuales
    s, d = _call("GET", f"/vehicles/{vid}")
    current = handle(s, d)
    if not current:
        press_enter(); return
    v = current.get("vehicle", {})

    print(f"\n  Deja en blanco para {YELLOW}mantener el valor actual{RESET}.")
    model    = input(f"  Modelo        [{v.get('model')}]: ").strip()
    battery  = input(f"  Batería (%)   [{v.get('battery')}]: ").strip()
    location = input(f"  Ubicación     [{v.get('location')}]: ").strip()
    price    = input(f"  Precio €/min  [{v.get('price_per_min')}]: ").strip()
    print(f"  Estados válidos: disponible / en_uso / mantenimiento")
    state    = input(f"  Estado        [{v.get('status')}]: ").strip()

    updates = {}
    if model:    updates["model"]         = model
    if location: updates["location"]      = location
    if state:    updates["status"]        = state
    if battery:
        try: updates["battery"] = int(battery)
        except ValueError: print_err("Batería debe ser entero."); press_enter(); return
    if price:
        try: updates["price_per_min"] = float(price)
        except ValueError: print_err("Precio debe ser decimal."); press_enter(); return

    if not updates:
        print_info("Sin cambios."); press_enter(); return

    s2, d2 = _call("PUT", f"/vehicles/{vid}", updates)
    handle(s2, d2)
    press_enter()


def admin_eliminar_vehiculo():
    header("Eliminar Patinete")
    vid     = input("  ID del patinete a eliminar: ").strip()
    confirm = input(f"  {RED}¿Confirmas eliminar este patinete? [s/N]{RESET}: ").strip().lower()
    if confirm != "s":
        print_info("Cancelado."); press_enter(); return

    s, d = _call("DELETE", f"/vehicles/{vid}")
    handle(s, d)
    press_enter()


def admin_todos_alquileres():
    header("Todos los Alquileres del Sistema")
    filtro = input("  Filtrar por estado (activo/finalizado, ENTER=todos): ").strip() or None
    params = {"status": filtro} if filtro else None
    s, d   = _call("GET", "/rentals/all", params=params)
    result = handle(s, d)
    if not result:
        press_enter(); return

    rentals = result.get("rentals", [])
    if not rentals:
        print_info("No hay alquileres.")
    else:
        print(f"\n  Total: {result.get('total')}")
        line()
        for r in rentals:
            estado = r.get("status", "").upper()
            color  = GREEN if estado == "FINALIZADO" else YELLOW
            print(f"\n  {color}[{estado}]{RESET}  Usuario: {r.get('username')}  |  {r.get('vehicle_model','')}")
            print(f"    Inicio : {r.get('start_time','—')}")
            print(f"    Fin    : {r.get('end_time') or 'En curso'}")
            coste = r.get('total_cost')
            print(f"    Coste  : {f'{coste} €' if coste else '—'}")
    press_enter()


def admin_ver_usuarios():
    header("Usuarios del Sistema")
    s, d   = _call("GET", "/users")
    result = handle(s, d)
    if not result:
        press_enter(); return

    users = result.get("users", [])
    print(f"\n  {BOLD}{'ID':<26} {'Usuario':<18} {'Email':<28} {'Rol':<8} Estado{RESET}")
    line()
    for u in users:
        estado = f"{GREEN}Activo{RESET}" if u.get("active") else f"{RED}Bloqueado{RESET}"
        print(f"  {u['_id']:<26} {u['username']:<18} {u['email']:<28} {u.get('role',''):<8} {estado}")
    press_enter()


def admin_toggle_usuario():
    header("Activar / Desactivar Usuario")
    uid = input("  ID del usuario: ").strip()
    s, d = _call("PUT", f"/users/{uid}/toggle")
    handle(s, d)
    press_enter()


# ================================================================
#  MENÚS
# ================================================================
def menu_principal():
    """Menú sin sesión activa."""
    while True:
        header("Bienvenido")
        print(f"\n  {WHITE}1.{RESET} Iniciar sesión")
        print(f"  {WHITE}2.{RESET} Crear cuenta")
        print(f"  {WHITE}3.{RESET} Salir")
        line()
        opt = input(f"  {BOLD}Opción:{RESET} ").strip()

        if opt == "1":
            screen_login()
            if SESSION["token"]:
                return              # ir al menú según rol
        elif opt == "2":
            screen_register()
        elif opt == "3":
            clear_screen()
            print(f"\n  {GREEN}¡Hasta pronto! 🛴{RESET}\n")
            sys.exit(0)
        else:
            print_err("Opción no válida.")
            press_enter()


def menu_usuario():
    """Menú para usuarios estándar."""
    OPS = {
        "1": user_ver_patinetes,
        "2": user_alquilar,
        "3": user_finalizar_alquiler,
        "4": user_historial,
        "5": user_mi_perfil,
    }
    while SESSION["token"]:
        header(f"Panel Usuario  —  {SESSION['username']}")
        print(f"\n  {WHITE}1.{RESET} Ver patinetes disponibles")
        print(f"  {WHITE}2.{RESET} Alquilar un patinete")
        print(f"  {WHITE}3.{RESET} Finalizar mi alquiler activo")
        print(f"  {WHITE}4.{RESET} Mi historial de alquileres")
        print(f"  {WHITE}5.{RESET} Mi perfil")
        print(f"  {WHITE}6.{RESET} Cerrar sesión")
        line()
        opt = input(f"  {BOLD}Opción:{RESET} ").strip()

        if opt in OPS:
            OPS[opt]()
        elif opt == "6":
            do_logout()
            return
        else:
            print_err("Opción no válida.")
            press_enter()


def menu_admin():
    """Menú para administradores."""
    OPS = {
        "1": admin_ver_vehiculos,
        "2": admin_crear_vehiculo,
        "3": admin_editar_vehiculo,
        "4": admin_eliminar_vehiculo,
        "5": admin_todos_alquileres,
        "6": admin_ver_usuarios,
        "7": admin_toggle_usuario,
    }
    while SESSION["token"]:
        header(f"Panel ADMIN  —  {SESSION['username']}")
        print(f"\n  {CYAN}── Vehículos ──────────────────{RESET}")
        print(f"  {WHITE}1.{RESET} Ver todos los patinetes")
        print(f"  {WHITE}2.{RESET} Crear patinete")
        print(f"  {WHITE}3.{RESET} Editar patinete")
        print(f"  {WHITE}4.{RESET} Eliminar patinete")
        print(f"\n  {CYAN}── Alquileres ─────────────────{RESET}")
        print(f"  {WHITE}5.{RESET} Ver todos los alquileres")
        print(f"\n  {CYAN}── Usuarios ───────────────────{RESET}")
        print(f"  {WHITE}6.{RESET} Ver todos los usuarios")
        print(f"  {WHITE}7.{RESET} Activar / desactivar usuario")
        print(f"\n  {WHITE}8.{RESET} Cerrar sesión")
        line()
        opt = input(f"  {BOLD}Opción:{RESET} ").strip()

        if opt in OPS:
            OPS[opt]()
        elif opt == "8":
            do_logout()
            return
        else:
            print_err("Opción no válida.")
            press_enter()


# ================================================================
#  PUNTO DE ENTRADA
# ================================================================
def main():
    # Habilitar colores ANSI en Windows
    if os.name == "nt":
        os.system("color")

    try:
        while True:
            menu_principal()
            # Bucle de sesión activa
            while SESSION["token"]:
                if SESSION["role"] == "admin":
                    menu_admin()
                else:
                    menu_usuario()

    except KeyboardInterrupt:
        clear_screen()
        print(f"\n  {GREEN}Aplicación cerrada. ¡Hasta pronto! 🛴{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
