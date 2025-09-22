import os
import logging
from flask import Flask, render_template
from .extensions import db, migrate

logger = logging.getLogger(__name__)

def env_to_bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes")

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    try:
        app.config.from_pyfile("config.py", silent=True)
    except Exception:
        pass
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY",
        app.config.get("SECRET_KEY", "dev-secret-change-me")
    )
    app.config["SESSION_COOKIE_SECURE"] = env_to_bool("SESSION_COOKIE_SECURE", default=False)
    app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get(
        "SESSION_COOKIE_SAMESITE",
        app.config.get("SESSION_COOKIE_SAMESITE", "Lax")
    )
    database_url = os.environ.get("DATABASE_URL") or app.config.get("SQLALCHEMY_DATABASE_URI")
    if database_url:
        if database_url.startswith("sqlite:///") and "\\" in database_url:
            database_url = database_url.replace("\\", "/")
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["GOOGLE_OAUTH_CLIENT_ID"] = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", app.config.get("GOOGLE_OAUTH_CLIENT_ID"))
    app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", app.config.get("GOOGLE_OAUTH_CLIENT_SECRET"))
    app.config["GOOGLE_OAUTH_REDIRECT_URI"] = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", app.config.get("GOOGLE_OAUTH_REDIRECT_URI"))
    app.config["GOOGLE_OAUTH_CLIENT_CONFIG_JSON"] = os.environ.get("GOOGLE_OAUTH_CLIENT_CONFIG_JSON", app.config.get("GOOGLE_OAUTH_CLIENT_CONFIG_JSON"))
    try:
        db.init_app(app)
    except Exception:
        logger.exception("Failed to initialize db extension")

    try:
        migrate.init_app(app, db)
    except Exception:
        logger.debug("Flask-Migrate not configured or init failed (continuing)")
    try:
        from .google_fit import google_fit_bp
        app.register_blueprint(google_fit_bp, url_prefix="/google-fit")
        logger.info("Registered blueprint 'google_fit' at /google-fit")
    except Exception:
        logger.exception("Failed to register google_fit blueprint")
    try:
        from .meals import meals_bp
        app.register_blueprint(meals_bp, url_prefix="/meals")
        logger.info("Registered blueprint 'meals' at /meals")
    except Exception:
        logger.exception("Failed to import/register 'meals' blueprint")
    try:
        from .leaderboard import leaderboard_bp
        app.register_blueprint(leaderboard_bp, url_prefix="/leaderboard")
        logger.info("Registered blueprint 'leaderboard' at /leaderboard")
    except Exception:
        logger.exception("Failed to import/register 'leaderboard' blueprint")
    try:
        from .auth import auth_bp
        app.register_blueprint(auth_bp)
        logger.info("Registered blueprint 'auth'")
    except Exception:
        logger.exception("Failed to import/register 'auth' blueprint")
    try:
        from .profile import profile_bp
        app.register_blueprint(profile_bp, url_prefix="/profile")
        logger.info("Registered blueprint 'profile' at /profile")
    except Exception:
        logger.exception("Failed to import/register 'profile' blueprint")
    try:
        from .activities import activities_bp
        app.register_blueprint(activities_bp, url_prefix="/activities")
        logger.info("Registered blueprint 'activities' at /activities")
    except Exception:
        logger.exception("Failed to import/register 'activities' blueprint")
    @app.route("/")
    def index():
        return render_template("index.html")
    return app
