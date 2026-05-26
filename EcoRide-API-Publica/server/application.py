"""
╔══════════════════════════════════════════════════════════╗
║        EcoRide — API REST de Alquiler de Patinetes       ║
║        Flask + MongoDB + JWT                             ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sys
import uuid
import random
import bcrypt
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.utils import secure_filename

# En Windows, la salida por defecto puede ser cp1252 y fallar con emojis.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ================================================================
#  INICIALIZACIÓN DE LA APP
# ================================================================
app = Flask(__name__, static_folder="static", static_url_path="/static")

PROFILE_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads", "profiles")

app.config["JWT_SECRET_KEY"]          = os.environ.get("JWT_SECRET_KEY", "ecoride-dev-secret-2025")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
app.config["JWT_TOKEN_LOCATION"]      = ["headers"]
app.config["JWT_HEADER_NAME"]         = "Authorization"
app.config["JWT_HEADER_TYPE"]         = "Bearer"

jwt = JWTManager(app)

db_available = True


# ================================================================
#  CONEXIÓN A MONGODB
#  - Local:  mongodb://localhost:27017/
# ================================================================
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME   = os.environ.get("DB_NAME",   "ecoride_db")

print(f"\n🔌  Conectando a MongoDB en: {MONGO_URI}")

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=6000)
    mongo_client.admin.command("ping")
    db = mongo_client[DB_NAME]
    print(f"✅  Conexión exitosa → base de datos: '{DB_NAME}'\n")
except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
    db_available = False
    db = None
    col_users = None
    col_vehicles = None
    col_rentals = None
    print(f"\n❌  ERROR: No se pudo conectar a MongoDB.")
    print(f"    Detalle: {exc}")
    print(f"    Solución:")
    print(f"      · Si usas MongoDB local, asegúrate de que 'mongod' está corriendo.")
    print(f"      · Si usas Atlas, revisa usuario, contraseña y que tu IP esté en Network Access.")
    print(f"      · URI actual: {MONGO_URI}\n")

# Colecciones
if db_available:
    col_users    = db["users"]
    col_vehicles = db["vehicles"]
    col_rentals  = db["rentals"]

# Estados válidos de un patinete
VEHICLE_STATES = ("disponible", "en_uso", "mantenimiento")


# ================================================================
#  HELPERS
# ================================================================
def to_json(doc: dict) -> dict:
    """Convierte ObjectId a str para poder devolver JSON."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    for field in ("start_time", "end_time"):
        value = doc.get(field)
        if isinstance(value, datetime):
            doc[field] = value.strftime("%Y-%m-%d %H:%M")
    return doc

def parse_datetime(value):
    """Convierte un valor de fecha de alquiler a datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for parser in (
            datetime.fromisoformat,
            lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M"),
        ):
            try:
                return parser(value)
            except ValueError:
                continue
    raise ValueError("Formato de fecha inválido.")

def parse_oid(id_str: str):
    """Devuelve ObjectId o None si el string no es válido."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None

def bad_request(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code

def ok(data: dict, code: int = 200):
    data["ok"] = True
    return jsonify(data), code


def user_response(user: dict | None) -> dict | None:
    if not user:
        return None
    payload = to_json(dict(user))
    payload["profile_picture"] = payload.get("profile_picture") or None
    return payload


def random_madrid_coordinates() -> tuple[float, float]:
    latitude = round(random.uniform(40.41, 40.45), 6)
    longitude = round(random.uniform(-3.75, -3.70), 6)
    return latitude, longitude


def normalize_vehicle(vehicle: dict) -> dict:
    payload = to_json(vehicle)
    payload["latitude"] = float(payload.get("latitude", 0.0))
    payload["longitude"] = float(payload.get("longitude", 0.0))
    return payload


def is_valid_image_upload(uploaded_file) -> tuple[bool, str | None]:
    if not uploaded_file or not uploaded_file.filename:
        return False, None

    filename = secure_filename(uploaded_file.filename)
    if not filename:
        return False, None

    content = uploaded_file.read()
    uploaded_file.seek(0)

    if not content:
        return False, None

    if content.startswith(b"\xff\xd8\xff"):
        return True, ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return True, ".gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return True, ".webp"
    if content.startswith(b"BM"):
        return True, ".bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return True, ".tiff"

    return False, None


def db_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not db_available:
            return bad_request("Servicio temporalmente no disponible. MongoDB no está accesible.", 503)
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """Decorador: requiere token JWT válido con role='admin'."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return bad_request("Acceso denegado. Solo administradores.", 403)
        return fn(*args, **kwargs)
    return wrapper


# ================================================================
#  MANEJADORES DE ERROR JWT
# ================================================================
@jwt.unauthorized_loader
def missing_token(reason):
    return jsonify({"ok": False, "error": f"Token requerido: {reason}"}), 401

@jwt.expired_token_loader
def expired_token(header, payload):
    return jsonify({"ok": False, "error": "Token expirado. Inicia sesión de nuevo."}), 401

@jwt.invalid_token_loader
def invalid_token(reason):
    return jsonify({"ok": False, "error": f"Token inválido: {reason}"}), 422


# ================================================================
#  MANEJADORES DE ERROR HTTP GLOBALES
# ================================================================
@app.errorhandler(404)
def err_404(e):
    return jsonify({"ok": False, "error": "Ruta no encontrada."}), 404

@app.errorhandler(405)
def err_405(e):
    return jsonify({"ok": False, "error": "Método HTTP no permitido en esta ruta."}), 405

@app.errorhandler(500)
def err_500(e):
    return jsonify({"ok": False, "error": "Error interno del servidor."}), 500


# ================================================================
#  RUTA DE ESTADO  (útil para comprobar que la API responde)
# ================================================================
@app.route("/", methods=["GET"])
def health():
    return ok({
        "message" : "🛴 EcoRide API en línea",
        "version" : "1.0",
        "database": DB_NAME,
        "endpoints": {
            "auth"    : ["/auth/register [POST]", "/auth/login [POST]"],
            "vehicles": ["/vehicles [GET|POST]", "/vehicles/<id> [GET|PUT|DELETE]"],
            "rentals" : ["/rentals/start [POST]", "/rentals/end/<id> [PUT]",
                         "/rentals/active [GET]", "/rentals/my-history [GET]",
                         "/rentals/all [GET] (admin)"],
            "users"   : ["/users/me [GET]", "/users [GET] (admin)",
                         "/users/<id>/toggle [PUT] (admin)"],
        }
    })


# ================================================================
#  AUTH  — /auth
# ================================================================

@app.route("/auth/register", methods=["POST"])
@db_required
def register():
    """
    POST /auth/register
    {
        "username": "pepe",
        "email":    "pepe@mail.com",
        "password": "Segura123!"
    }
    """
    data = request.get_json(silent=True) or {}

    # Validar campos obligatorios
    for field in ("username", "email", "password"):
        if not str(data.get(field, "")).strip():
            return bad_request(f"El campo '{field}' es obligatorio.")

    username = data["username"].strip()
    email    = data["email"].strip().lower()
    password = data["password"]

    if len(password) < 6:
        return bad_request("La contraseña debe tener al menos 6 caracteres.")

    if col_users.find_one({"email": email}):
        return bad_request("Ya existe una cuenta con ese email.")
    if col_users.find_one({"username": username}):
        return bad_request("Ese nombre de usuario ya está en uso.")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    # El primer usuario registrado (además del admin seed) siempre es "user"
    # Para crear un admin usa el script de seed o MongoDB Compass directamente
    new_user = {
        "username"  : username,
        "email"     : email,
        "password"  : hashed,
        "role"      : "user",
        "active"    : True,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = col_users.insert_one(new_user)

    return ok({"message": "Cuenta creada correctamente.", "user_id": str(result.inserted_id)}, 201)


@app.route("/auth/login", methods=["POST"])
@db_required
def login():
    """
    POST /auth/login
    { "email": "pepe@mail.com", "password": "Segura123!" }
    """
    data = request.get_json(silent=True) or {}
    email    = str(data.get("email",    "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return bad_request("Email y contraseña son obligatorios.")

    user = col_users.find_one({"email": email})
    if not user:
        return bad_request("Credenciales incorrectas.", 401)

    if not bcrypt.checkpw(password.encode(), user["password"]):
        return bad_request("Credenciales incorrectas.", 401)

    if not user.get("active", True):
        return bad_request("Cuenta desactivada. Contacta con el administrador.", 403)

    token = create_access_token(
        identity=str(user["_id"]),
        additional_claims={
            "role"    : user["role"],
            "username": user["username"],
        }
    )

    return jsonify({
        "ok"          : True,
        "message"     : f"¡Bienvenido, {user['username']}!",
        "access_token": token,
        "role"        : str(user["role"]).upper(),
        "username"    : user["username"],
    }), 200


# ================================================================
#  VEHÍCULOS  — /vehicles
# ================================================================

@app.route("/vehicles", methods=["GET"])
@db_required
@jwt_required()
def list_vehicles():
    """
    GET /vehicles
    GET /vehicles?status=mantenimiento  (solo admins pueden filtrar todos los estados)
    """
    role   = get_jwt().get("role")
    status = request.args.get("status", "").strip()

    if role == "admin":
        query = {"status": status} if status else {}
    else:
        # Los usuarios normales SOLO ven los disponibles
        query = {"status": "disponible"}

    vehicles = [normalize_vehicle(v) for v in col_vehicles.find(query)]
    return ok({"vehicles": vehicles})


@app.route("/vehicles/<vehicle_id>", methods=["GET"])
@db_required
@jwt_required()
def get_vehicle(vehicle_id):
    """GET /vehicles/<id>"""
    oid = parse_oid(vehicle_id)
    if not oid:
        return bad_request("ID de vehículo inválido.")

    vehicle = col_vehicles.find_one({"_id": oid})
    if not vehicle:
        return bad_request("Vehículo no encontrado.", 404)

    return ok({"vehicle": normalize_vehicle(vehicle)})


@app.route("/vehicles", methods=["POST"])
@db_required
@admin_required
def create_vehicle():
    """
    POST /vehicles  [Solo admin]
    {
        "model"        : "Xiaomi Mi Pro 2",
        "battery"      : 90,
        "location"     : "Plaza Mayor",
        "price_per_min": 0.15
    }
    """
    data = request.get_json(silent=True) or {}

    for field in ("model", "battery", "location", "price_per_min"):
        if data.get(field) is None:
            return bad_request(f"El campo '{field}' es obligatorio.")

    try:
        battery       = int(data["battery"])
        price_per_min = float(data["price_per_min"])
    except (ValueError, TypeError):
        return bad_request("'battery' debe ser entero y 'price_per_min' decimal.")

    if not (0 <= battery <= 100):
        return bad_request("La batería debe estar entre 0 y 100.")
    if price_per_min <= 0:
        return bad_request("El precio por minuto debe ser positivo.")

    if data.get("latitude") is None or data.get("longitude") is None:
        latitude, longitude = random_madrid_coordinates()
    else:
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (ValueError, TypeError):
            return bad_request("'latitude' y 'longitude' deben ser numéricos.")

    vehicle = {
        "model"        : str(data["model"]).strip(),
        "battery"      : battery,
        "location"     : str(data["location"]).strip(),
        "price_per_min": price_per_min,
        "latitude"     : latitude,
        "longitude"    : longitude,
        "status"       : "disponible",
        "created_at"   : datetime.utcnow().isoformat(),
    }
    result = col_vehicles.insert_one(vehicle)
    return ok({"message": "Vehículo creado correctamente.", "vehicle_id": str(result.inserted_id)}, 201)


@app.route("/vehicles/<vehicle_id>", methods=["PUT"])
@db_required
@admin_required
def update_vehicle(vehicle_id):
    """
    PUT /vehicles/<id>  [Solo admin]
    Envía solo los campos que quieres actualizar.
    """
    oid = parse_oid(vehicle_id)
    if not oid:
        return bad_request("ID de vehículo inválido.")

    if not col_vehicles.find_one({"_id": oid}):
        return bad_request("Vehículo no encontrado.", 404)

    data    = request.get_json(silent=True) or {}
    allowed = {"model", "battery", "location", "price_per_min", "status", "latitude", "longitude"}
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return bad_request("No se proporcionaron campos válidos para actualizar.")

    if "status" in updates and updates["status"] not in VEHICLE_STATES:
        return bad_request(f"Estado inválido. Valores permitidos: {VEHICLE_STATES}")

    if "latitude" in updates:
        try:
            updates["latitude"] = float(updates["latitude"])
        except (ValueError, TypeError):
            return bad_request("'latitude' debe ser numérico.")

    if "longitude" in updates:
        try:
            updates["longitude"] = float(updates["longitude"])
        except (ValueError, TypeError):
            return bad_request("'longitude' debe ser numérico.")

    col_vehicles.update_one({"_id": oid}, {"$set": updates})
    return ok({"message": "Vehículo actualizado correctamente."})


@app.route("/vehicles/<vehicle_id>", methods=["DELETE"])
@db_required
@admin_required
def delete_vehicle(vehicle_id):
    """DELETE /vehicles/<id>  [Solo admin]"""
    oid = parse_oid(vehicle_id)
    if not oid:
        return bad_request("ID de vehículo inválido.")

    vehicle = col_vehicles.find_one({"_id": oid})
    if not vehicle:
        return bad_request("Vehículo no encontrado.", 404)

    if vehicle.get("status") == "en_uso":
        return bad_request("No puedes eliminar un vehículo que está en uso.")

    col_vehicles.delete_one({"_id": oid})
    return ok({"message": "Vehículo eliminado correctamente."})


# ================================================================
#  ALQUILERES  — /rentals
# ================================================================

@app.route("/rentals/start", methods=["POST"])
@db_required
@jwt_required()
def start_rental():
    """
    POST /rentals/start
    { "vehicle_id": "<id>" }
    """
    user_id  = get_jwt_identity()
    claims   = get_jwt()
    data     = request.get_json(silent=True) or {}
    vehicle_id = str(data.get("vehicle_id", "")).strip()

    if not vehicle_id:
        return bad_request("Debes indicar el 'vehicle_id'.")

    # El usuario no puede tener dos alquileres activos a la vez
    if col_rentals.find_one({"user_id": user_id, "status": "activo"}):
        return bad_request("Ya tienes un alquiler activo. Finalízalo primero.")

    oid = parse_oid(vehicle_id)
    if not oid:
        return bad_request("ID de vehículo inválido.")

    vehicle = col_vehicles.find_one({"_id": oid})
    if not vehicle:
        return bad_request("Vehículo no encontrado.", 404)
    if vehicle["status"] != "disponible":
        return bad_request(f"El vehículo no está disponible (estado actual: '{vehicle['status']}').")

    rental = {
        "user_id"      : user_id,
        "username"     : claims.get("username"),
        "vehicle_id"   : vehicle_id,
        "vehicle_model": vehicle["model"],
        "price_per_min": vehicle["price_per_min"],
        "start_time"   : datetime.utcnow(),
        "end_time"     : None,
        "duration_min" : None,
        "total_cost"   : None,
        "status"       : "activo",
    }
    result = col_rentals.insert_one(rental)
    col_vehicles.update_one({"_id": oid}, {"$set": {"status": "en_uso"}})

    return ok({
        "message"  : "¡Alquiler iniciado! Buen viaje 🛴",
        "rental_id": str(result.inserted_id),
    }, 201)


@app.route("/rentals/end/<rental_id>", methods=["PUT"])
@db_required
@jwt_required()
def end_rental(rental_id):
    """PUT /rentals/end/<rental_id>  — Finaliza tu alquiler activo."""
    user_id = get_jwt_identity()
    oid     = parse_oid(rental_id)
    if not oid:
        return bad_request("ID de alquiler inválido.")

    rental = col_rentals.find_one({"_id": oid})
    if not rental:
        return bad_request("Alquiler no encontrado.", 404)
    if rental["user_id"] != user_id:
        return bad_request("Este alquiler no te pertenece.", 403)
    if rental["status"] != "activo":
        return bad_request("Este alquiler ya está finalizado.")

    try:
        start = parse_datetime(rental["start_time"])
    except ValueError:
        return bad_request("La fecha de inicio del alquiler es inválida.", 500)
    end      = datetime.utcnow()
    duration = max(1.0, round((end - start).total_seconds() / 60, 2))
    cost     = round(duration * rental["price_per_min"], 2)

    col_rentals.update_one({"_id": oid}, {"$set": {
        "end_time"    : end.isoformat(),
        "duration_min": duration,
        "total_cost"  : cost,
        "status"      : "finalizado",
    }})

    # Devolver el patinete a disponible
    v_oid = parse_oid(rental["vehicle_id"])
    if v_oid:
        col_vehicles.update_one({"_id": v_oid}, {"$set": {"status": "disponible"}})

    return ok({
        "message"     : "Alquiler finalizado. ¡Gracias por usar EcoRide!",
        "duration_min": duration,
        "total_cost"  : cost,
    })


@app.route("/rentals/active", methods=["GET"])
@db_required
@jwt_required()
def active_rental():
    """GET /rentals/active — Tu alquiler activo."""
    user_id = get_jwt_identity()
    rental  = col_rentals.find_one({"user_id": user_id, "status": "activo"})
    if not rental:
        return bad_request("No tienes ningún alquiler activo.", 404)
    return ok({
        "rental": {
            "vehicle_model": rental.get("vehicle_model"),
            "price_per_min": rental.get("price_per_min"),
            "start_time": parse_datetime(rental.get("start_time")).strftime("%Y-%m-%d %H:%M"),
        }
    })


@app.route("/rentals/my-history", methods=["GET"])
@db_required
@jwt_required()
def my_history():
    """GET /rentals/my-history — Tu historial completo de alquileres."""
    user_id = get_jwt_identity()
    rentals = [to_json(r) for r in col_rentals.find({"user_id": user_id}).sort("start_time", -1)]
    return ok({"rentals": rentals, "total": len(rentals)})


@app.route("/rentals/all", methods=["GET"])
@db_required
@admin_required
def all_rentals():
    """GET /rentals/all  [Solo admin] — Todos los alquileres del sistema."""
    status = request.args.get("status", "").strip()
    query  = {"status": status} if status else {}
    rentals = [to_json(r) for r in col_rentals.find(query).sort("start_time", -1)]
    return ok({"rentals": rentals, "total": len(rentals)})


# ================================================================
#  USUARIOS  — /users
# ================================================================

@app.route("/users/me", methods=["GET"])
@db_required
@jwt_required()
def my_profile():
    """GET /users/me — Tu perfil."""
    oid  = parse_oid(get_jwt_identity())
    user = col_users.find_one({"_id": oid}, {"password": 0})
    if not user:
        return bad_request("Usuario no encontrado.", 404)
    return ok({"user": user_response(user)})


@app.route("/users/me", methods=["PUT"])
@db_required
@jwt_required()
def update_my_profile():
    """PUT /users/me — Actualiza datos básicos del perfil."""
    oid = parse_oid(get_jwt_identity())
    user = col_users.find_one({"_id": oid})
    if not user:
        return bad_request("Usuario no encontrado.", 404)

    data = request.get_json(silent=True) or {}
    updates = {}

    if "username" in data:
        username = str(data.get("username", "")).strip()
        if not username:
            return bad_request("El campo 'username' no puede estar vacío.")
        if username != user.get("username") and col_users.find_one({"username": username, "_id": {"$ne": oid}}):
            return bad_request("Ese nombre de usuario ya está en uso.")
        updates["username"] = username

    if "email" in data:
        email = str(data.get("email", "")).strip().lower()
        if not email:
            return bad_request("El campo 'email' no puede estar vacío.")
        if email != user.get("email") and col_users.find_one({"email": email, "_id": {"$ne": oid}}):
            return bad_request("Ya existe una cuenta con ese email.")
        updates["email"] = email

    if not updates:
        return bad_request("No se proporcionaron campos válidos para actualizar.")

    col_users.update_one({"_id": oid}, {"$set": updates})
    updated_user = col_users.find_one({"_id": oid}, {"password": 0})
    return ok({"user": user_response(updated_user)})


@app.route("/auth/profile/picture", methods=["POST"])
@db_required
@jwt_required()
def upload_profile_picture():
    """POST /auth/profile/picture — Sube la foto de perfil como multipart field 'picture'."""
    oid = parse_oid(get_jwt_identity())
    user = col_users.find_one({"_id": oid})
    if not user:
        return bad_request("Usuario no encontrado.", 404)

    picture = request.files.get("picture")
    is_valid, extension = is_valid_image_upload(picture)
    if not is_valid or not extension:
        return bad_request("El archivo enviado debe ser una imagen válida.")

    os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = os.path.join("uploads", "profiles", unique_filename).replace("\\", "/")
    absolute_path = os.path.join(PROFILE_UPLOAD_FOLDER, unique_filename)

    with open(absolute_path, "wb") as image_file:
        image_file.write(picture.read())

    col_users.update_one({"_id": oid}, {"$set": {"profile_picture": relative_path}})
    updated_user = col_users.find_one({"_id": oid}, {"password": 0})

    return ok({"user": user_response(updated_user)})


@app.route("/users", methods=["GET"])
@db_required
@admin_required
def list_users():
    """GET /users  [Solo admin] — Lista todos los usuarios."""
    users = [to_json(u) for u in col_users.find({}, {"password": 0})]
    return ok({"users": users, "total": len(users)})


@app.route("/users/<user_id>/toggle", methods=["PUT"])
@db_required
@admin_required
def toggle_user(user_id):
    """PUT /users/<id>/toggle  [Solo admin] — Activa o desactiva una cuenta."""
    oid  = parse_oid(user_id)
    if not oid:
        return bad_request("ID de usuario inválido.")

    user = col_users.find_one({"_id": oid})
    if not user:
        return bad_request("Usuario no encontrado.", 404)

    new_state = not user.get("active", True)
    col_users.update_one({"_id": oid}, {"$set": {"active": new_state}})
    estado = "activada" if new_state else "desactivada"
    return ok({"message": f"Cuenta {estado} correctamente.", "active": new_state})


# ================================================================
#  SEED — Datos iniciales (solo si las colecciones están vacías)
# ================================================================
def seed():
    """Inserta el admin y vehículos de ejemplo si no existen."""
    # ── Admin por defecto ──
    if not col_users.find_one({"email": "admin@ecoride.com"}):
        hashed = bcrypt.hashpw(b"Admin1234!", bcrypt.gensalt())
        col_users.insert_one({
            "username"  : "admin",
            "email"     : "admin@ecoride.com",
            "password"  : hashed,
            "role"      : "admin",
            "active"    : True,
            "profile_picture": None,
            "created_at": datetime.utcnow().isoformat(),
        })
        print("🔑  Admin creado  →  admin@ecoride.com  /  Admin1234!")

    # ── Patinetes de ejemplo ──
    patinetes = [
        {"model": "Xiaomi Mi Pro 2",  "battery": 95, "location": "Plaza Mayor",    "price_per_min": 0.15, "status": "disponible"},
        {"model": "Segway Ninebot E2","battery": 82, "location": "Puerta del Sol", "price_per_min": 0.18, "status": "disponible"},
        {"model": "Pure Air Pro",     "battery": 70, "location": "Atocha",         "price_per_min": 0.12, "status": "disponible"},
        {"model": "Cecotec Bongo S4", "battery": 45, "location": "Gran Vía",       "price_per_min": 0.10, "status": "mantenimiento"},
        {"model": "NIU KQi3 Pro",     "battery": 90, "location": "Retiro",         "price_per_min": 0.20, "status": "disponible"},
        {"model": "Xiaomi Essential", "battery": 88, "location": "Chamartín",      "price_per_min": 0.14, "status": "disponible"},
        {"model": "Segway F25E",      "battery": 76, "location": "Moncloa",        "price_per_min": 0.16, "status": "disponible"},
        {"model": "Cecotec Bongo Y65", "battery": 64, "location": "Lavapiés",       "price_per_min": 0.11, "status": "disponible"},
        {"model": "SmartGyro Ziro",    "battery": 58, "location": "Malasaña",       "price_per_min": 0.13, "status": "mantenimiento"},
        {"model": "Hiboy S2 Pro",      "battery": 91, "location": "La Latina",      "price_per_min": 0.19, "status": "disponible"},
        {"model": "Razor E Prime",     "battery": 67, "location": "Arganzuela",     "price_per_min": 0.15, "status": "disponible"},
        {"model": "Ninebot ES2",       "battery": 73, "location": "Cuzco",          "price_per_min": 0.17, "status": "disponible"},
        {"model": "Cecotec Bongo Z",   "battery": 49, "location": "Usera",          "price_per_min": 0.10, "status": "mantenimiento"},
        {"model": "Okai Neon",         "battery": 84, "location": "O'Donnell",      "price_per_min": 0.18, "status": "disponible"},
        {"model": "EverCross EV10K",   "battery": 62, "location": "Serrano",        "price_per_min": 0.12, "status": "disponible"},
        {"model": "Razor Power Core",  "battery": 55, "location": "Avenida América", "price_per_min": 0.09, "status": "disponible"},
        {"model": "Xiaomi 4 Pro",      "battery": 97, "location": "Sol",            "price_per_min": 0.21, "status": "disponible"},
        {"model": "Segway D18E",       "battery": 79, "location": "Nuevos Ministerios", "price_per_min": 0.16, "status": "disponible"},
        {"model": "Cecotec Bongo Z4",  "battery": 46, "location": "Legazpi",        "price_per_min": 0.10, "status": "mantenimiento"},
        {"model": "NIU KQi2 Pro",      "battery": 86, "location": "Príncipe Pío",   "price_per_min": 0.18, "status": "disponible"},
        {"model": "SmartGyro X2",      "battery": 68, "location": "Ventas",         "price_per_min": 0.14, "status": "disponible"},
    ]

    existing_models = {
        vehicle.get("model")
        for vehicle in col_vehicles.find({}, {"model": 1})
        if vehicle.get("model")
    }

    vehicles_to_insert = []
    for p in patinetes:
        if p["model"] in existing_models:
            continue
        latitude, longitude = random_madrid_coordinates()
        p["latitude"] = latitude
        p["longitude"] = longitude
        p["created_at"] = datetime.utcnow().isoformat()
        vehicles_to_insert.append(p)

    if vehicles_to_insert:
        col_vehicles.insert_many(vehicles_to_insert)
        print(f"🛴  {len(vehicles_to_insert)} patinetes de ejemplo creados.")


def update_existing_vehicle_coordinates():
    """Asigna coordenadas de prueba en Madrid a vehículos sin lat/lon."""
    updates = 0
    for vehicle in col_vehicles.find({}):
        missing_lat = "latitude" not in vehicle or vehicle.get("latitude") is None
        missing_lon = "longitude" not in vehicle or vehicle.get("longitude") is None
        if missing_lat or missing_lon:
            latitude, longitude = random_madrid_coordinates()
            col_vehicles.update_one(
                {"_id": vehicle["_id"]},
                {"$set": {"latitude": latitude, "longitude": longitude}},
            )
            updates += 1
    if updates:
        print(f"📍  Vehículos actualizados con coordenadas: {updates}")


if db_available:
    seed()
    update_existing_vehicle_coordinates()


# ================================================================
#  ARRANQUE
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("  🛴  EcoRide API  —  Iniciando...")
    print("=" * 55)
    print(f"\n  Servidor escuchando en  http://0.0.0.0:{port}")
    print(f"  Prueba en el navegador:  http://localhost:{port}/\n")
    app.run(host="0.0.0.0", port=port)
