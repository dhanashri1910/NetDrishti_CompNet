
"""NetDrishti - Intelligent Network Diagnosis & Management Platform."""

import os
import sys
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from config import Config
from models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


def init_database(app):
    """Create tables and the documented demo administrator."""
    with app.app_context():
        db.create_all()
        email = app.config["DEMO_ADMIN_EMAIL"]

        if not User.query.filter_by(email=email).first():
            db.session.add(
                User(
                    full_name="Demo Administrator",
                    email=email,
                    is_admin=True,
                    password_hash=generate_password_hash(
                        app.config["DEMO_ADMIN_PASSWORD"]
                    )
                )
            )
            db.session.commit()


def create_app(config_overrides=None):
    app = Flask(__name__)

    app.config.from_object(Config)

    if config_overrides:
        app.config.update(config_overrides)

    for folder in (
        app.config["UPLOAD_FOLDER"],
        app.config["REPORT_FOLDER"],
        os.path.join(Config.BASE_DIR, "instance")
    ):
        os.makedirs(folder, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from backend.auth import bp as auth_bp
    from backend.views import bp as views_bp
    from backend.api import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    init_database(app)

    return app


# VERCEL ENTRYPOINT: expose Flask application at module level
app = create_app()


if __name__ == "__main__":

    if "--init-db" in sys.argv:
        print("Database initialised at",
              app.config["SQLALCHEMY_DATABASE_URI"])
        print("Demo admin:", app.config["DEMO_ADMIN_EMAIL"])

    else:
        app.run(host="127.0.0.1", port=5000, debug=False)
