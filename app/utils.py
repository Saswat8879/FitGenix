from functools import wraps
from flask import session, redirect, url_for, flash, current_app
from .models import User
from .extensions import db

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)

def safe_div(a, b, default=0.0):
    try:
        return a / b
    except Exception:
        return default

def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(e):
        return ("Not Found", 404)
    @app.errorhandler(500)
    def server_error(e):
        current_app.logger.exception(e)
        return ("Server Error", 500)
