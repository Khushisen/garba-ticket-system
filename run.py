import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db

app = create_app(os.environ.get("APP_ENV", "development"))


@app.shell_context_processor
def make_shell_context():
    from app import models

    return {"db": db, "models": models}


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=app.config.get("DEBUG", False))
