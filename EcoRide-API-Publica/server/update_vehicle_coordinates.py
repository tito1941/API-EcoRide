import os
import random
from pymongo import MongoClient


MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "ecoride_db")


def random_madrid_coordinates() -> tuple[float, float]:
    latitude = round(random.uniform(40.41, 40.45), 6)
    longitude = round(random.uniform(-3.75, -3.70), 6)
    return latitude, longitude


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=6000)
    client.admin.command("ping")

    db = client[DB_NAME]
    col_vehicles = db["vehicles"]

    updated = 0
    for vehicle in col_vehicles.find({}):
        missing_lat = "latitude" not in vehicle or vehicle.get("latitude") is None
        missing_lon = "longitude" not in vehicle or vehicle.get("longitude") is None
        if missing_lat or missing_lon:
            lat, lon = random_madrid_coordinates()
            col_vehicles.update_one(
                {"_id": vehicle["_id"]},
                {"$set": {"latitude": lat, "longitude": lon}},
            )
            updated += 1

    print(f"Vehiculos actualizados con coordenadas: {updated}")


if __name__ == "__main__":
    main()
