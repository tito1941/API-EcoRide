# EcoRide 🛴 — Guía de Instalación Paso a Paso

## ¿Qué necesitas?
- Python 3.9 o superior
- MongoDB (local)

---

## PASO 1 — Instalar MongoDB

### Opción A: MongoDB Local (recomendado para clase)
1. Descarga en: https://www.mongodb.com/try/download/community
2. Instala con las opciones por defecto (en Windows instala el servicio automáticamente)
3. Listo. No hace falta configurar ninguna URI.

---

## PASO 2 — Configurar y arrancar el SERVIDOR

```cmd
:: Entrar en la carpeta del servidor
cd server

:: Instalar dependencias
pip install -r requirements.txt

:: Arrancar el servidor
python application.py
```

### ✅ Si todo fue bien, verás esto en la terminal:
```
===========================================================
  🛴  EcoRide API  —  Iniciando...
===========================================================
✅  Conexión exitosa → base de datos: 'ecoride_db'
🔑  Admin creado  →  admin@ecoride.com  /  Admin1234!
🛴  5 patinetes de ejemplo creados.

  Servidor escuchando en  http://0.0.0.0:5000
  Prueba en el navegador:  http://localhost:5000/
```

### Verificar en el navegador
Abre: `http://localhost:5000/`
Debes ver:
```json
{
  "ok": true,
  "message": "🛴 EcoRide API en línea",
  ...
}
```

---

## PASO 3 — Arrancar el CLIENTE

```cmd
:: Abrir una NUEVA terminal (deja el servidor corriendo)
cd client

:: Instalar dependencias
pip install -r requirements.txt

:: Arrancar el cliente
python main.py
```

---

## Credenciales por defecto

| Rol   | Email               | Contraseña  |
|-------|---------------------|-------------|
| Admin | admin@ecoride.com   | Admin1234!  |

Los usuarios nuevos se registran desde el propio cliente (siempre con rol "user").

---

## Endpoints de la API

| Método   | Ruta                        | Rol         | Descripción                      |
|----------|-----------------------------|-------------|----------------------------------|
| GET      | `/`                         | Público     | Estado de la API                 |
| POST     | `/auth/register`            | Público     | Registro de usuario              |
| POST     | `/auth/login`               | Público     | Login → devuelve JWT             |
| GET      | `/users/me`                 | User/Admin  | Mi perfil                        |
| GET      | `/users`                    | Admin       | Todos los usuarios               |
| PUT      | `/users/<id>/toggle`        | Admin       | Activar/desactivar cuenta        |
| GET      | `/vehicles`                 | User/Admin  | Ver patinetes                    |
| GET      | `/vehicles/<id>`            | User/Admin  | Detalle de patinete              |
| POST     | `/vehicles`                 | Admin       | Crear patinete                   |
| PUT      | `/vehicles/<id>`            | Admin       | Editar patinete                  |
| DELETE   | `/vehicles/<id>`            | Admin       | Eliminar patinete                |
| POST     | `/rentals/start`            | User        | Iniciar alquiler                 |
| PUT      | `/rentals/end/<id>`         | User        | Finalizar alquiler               |
| GET      | `/rentals/active`           | User        | Mi alquiler activo               |
| GET      | `/rentals/my-history`       | User        | Mi historial                     |
| GET      | `/rentals/all`              | Admin       | Todos los alquileres             |

---

## Colecciones MongoDB

### users
```json
{
  "_id": "ObjectId",
  "username": "pepe",
  "email": "pepe@mail.com",
  "password": "<bcrypt hash>",
  "role": "user | admin",
  "active": true,
  "created_at": "2025-01-01T10:00:00"
}
```

### vehicles
```json
{
  "_id": "ObjectId",
  "model": "Xiaomi Mi Pro 2",
  "battery": 95,
  "location": "Plaza Mayor",
  "price_per_min": 0.15,
  "status": "disponible | en_uso | mantenimiento",
  "created_at": "2025-01-01T10:00:00"
}
```

### rentals
```json
{
  "_id": "ObjectId",
  "user_id": "<ref users._id>",
  "username": "pepe",
  "vehicle_id": "<ref vehicles._id>",
  "vehicle_model": "Xiaomi Mi Pro 2",
  "price_per_min": 0.15,
  "start_time": "2025-01-01T10:00:00",
  "end_time": "2025-01-01T10:30:00",
  "duration_min": 30.0,
  "total_cost": 4.5,
  "status": "activo | finalizado"
}
```
