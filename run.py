import logging
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db

app = create_app(os.environ.get("APP_ENV", "development"))

# Create any missing tables on startup. This is idempotent (existing tables are
# left untouched) and is needed because gunicorn imports `app` from this module
# and never executes the `if __name__ == "__main__"` block below.
# For schema *changes* later on, use Flask-Migrate instead.
with app.app_context():
    try:
        db.create_all()
    except Exception:  # e.g. two gunicorn workers racing to create tables
        logging.getLogger(__name__).warning("db.create_all() skipped/failed", exc_info=True)


@app.shell_context_processor
def make_shell_context():
    from app import models

    return {"db": db, "models": models}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=app.config.get("DEBUG", False))