import importlib.util
import os


BASE_DIR = os.path.dirname(__file__)
NESTED_APP_PATH = os.path.join(BASE_DIR, "..", "EcoRide-API-Publica", "server", "application.py")

spec = importlib.util.spec_from_file_location("ecoride_nested_application", NESTED_APP_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("No se pudo cargar la aplicación anidada.")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app