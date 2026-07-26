"""ASGI entrypoint.

Deployment platforms look for a top-level ``app`` in ``main.py`` at the
repository root, and many auto-detectors will not import a package submodule.
The application itself lives in ``backend/`` and uses relative imports, so
loading ``backend/main.py`` directly as a script fails — this module imports it
properly as part of the package and re-exports the instance.

Any of the following now work:

    uvicorn main:app --host 0.0.0.0 --port 8001
    gunicorn -k uvicorn.workers.UvicornWorker main:app
    python main.py
    python -m backend.main
"""

from backend.config import HOST, PORT
from backend.main import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
