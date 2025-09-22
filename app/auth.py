import logging
from datetime import datetime, date
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, current_app, jsonify
from .extensions import db, bcrypt
from .models import User

auth_bp = Blueprint("auth", __name__, template_folder="templates")
logger = logging.getLogger(__name__)
_ACTIVITY_LEVEL_MAP = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

def _coerce_activity_multiplier(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        pass
    v = str(value).strip().lower()
    if not v:
        return None
    if v in _ACTIVITY_LEVEL_MAP:
        return float(_ACTIVITY_LEVEL_MAP[v])
    for key in _ACTIVITY_LEVEL_MAP:
        if key in v:
            return float(_ACTIVITY_LEVEL_MAP[key])
    return None

def _parse_birth_date(value):
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        pass
    formats = ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d")
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.date()
    except Exception:
        pass
    return None

def _allowed_user_columns():
    """Return set of allowed column names for User to avoid passing invalid kwargs."""
    try:
        return {c.name for c in User.__table__.columns}
    except Exception:
        return {
            "id", "email", "password_hash", "full_name", "sex", "height_cm", "weight_kg",
            "birth_date", "activity_multiplier", "activity_level", "goal", "target_calories",
            "google_tokens", "steps", "avg_bpm", "sleep_minutes", "raw_payload", "created_at"
        }

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        try:
            return render_template("auth/register.html")
        except Exception:
            try:
                return render_template("register.html")
            except Exception:
                return (
                    "<h3>Register</h3>"
                    "<p>No register template found. Please POST JSON to /register or add a template.</p>"
                )
    data = request.get_json(silent=True) or request.form or {}
    def _get(k):
        return data.get(k) if isinstance(data, dict) else data.get(k)

    email = ( _get("email") or "" ).strip().lower()
    password = _get("password") or _get("pw") or ""
    full_name = _get("full_name") or _get("name") or ""
    sex = _get("sex") or "male"
    birth_date_raw = _get("birth_date") or None
    birth_date = _parse_birth_date(birth_date_raw)
    try:
        height_cm = float(_get("height_cm")) if _get("height_cm") not in (None, "") else None
    except Exception:
        height_cm = None
    try:
        weight_kg = float(_get("weight_kg")) if _get("weight_kg") not in (None, "") else None
    except Exception:
        weight_kg = None
    activity_multiplier = None
    if _get("activity_multiplier") not in (None, ""):
        activity_multiplier = _coerce_activity_multiplier(_get("activity_multiplier"))
    elif _get("activity_level") not in (None, ""):
        activity_multiplier = _coerce_activity_multiplier(_get("activity_level"))

    goal = _get("goal") or "maintain"
    if not email or not password:
        msg = "Email and password are required."
        if request.is_json:
            return jsonify({"error": msg}), 400
        flash(msg, "warning")
        return redirect(url_for("auth.register"))
    existing = User.query.filter_by(email=email).first()
    if existing:
        msg = "A user with that email already exists."
        if request.is_json:
            return jsonify({"error": msg}), 409
        flash(msg, "warning")
        return redirect(url_for("auth.register"))
    try:
        pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    except Exception:
        pwh = bcrypt.generate_password_hash(password)
        pw_hash = pwh.decode("utf-8") if isinstance(pwh, (bytes, bytearray)) else str(pwh)
    user_kwargs = {
        "email": email,
        "password_hash": pw_hash,
        "full_name": full_name,
        "sex": sex,
        "birth_date": birth_date if birth_date else None,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "activity_multiplier": activity_multiplier,
        "goal": goal,
    }

    allowed = _allowed_user_columns()
    filtered_kwargs = {k: v for k, v in user_kwargs.items() if k in allowed}

    try:
        user = User(**filtered_kwargs)
        db.session.add(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to create user: %s", exc)
        msg = "Failed to register user."
        if request.is_json:
            return jsonify({"error": msg}), 500
        flash(msg, "danger")
        return redirect(url_for("auth.register"))

    if request.is_json:
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email}}), 201

    flash("Registration successful. Please log in.", "success")
    return redirect(url_for("auth.login"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        try:
            return render_template("auth/login.html")
        except Exception:
            try:
                return render_template("login.html")
            except Exception:
                return (
                    "<h3>Login</h3>"
                    "<p>No login template found. Please POST JSON to /login or add a template.</p>"
                )

    data = request.get_json(silent=True) or request.form or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user:
        msg = "Invalid credentials."
        if request.is_json:
            return jsonify({"error": msg}), 401
        flash(msg, "danger")
        return redirect(url_for("auth.login"))

    try:
        ok = bcrypt.check_password_hash(user.password_hash, password)
    except Exception:
        ok = False

    if not ok:
        msg = "Invalid credentials."
        if request.is_json:
            return jsonify({"error": msg}), 401
        flash(msg, "danger")
        return redirect(url_for("auth.login"))

    session["user_id"] = user.id
    if request.is_json:
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email}}), 200

    flash("Logged in successfully.", "success")
    return redirect(url_for("meals.index"))

@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.pop("user_id", None)
    if request.is_json:
        return jsonify({"ok": True}), 200
    flash("Logged out.", "success")
    return redirect(url_for("auth.login"))
