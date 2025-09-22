from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from .extensions import db
from .models import User
from .nutrition import compute_bmr, predict_target_from_model
from .utils import login_required, get_current_user
from datetime import datetime

profile_bp = Blueprint("profile", __name__, template_folder="templates")

@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    if request.method == "GET":
        return render_template("profile.html", user=user)
    data = request.form
    try:
        height_cm = float(data.get("height_cm") or 0) or None
    except:
        height_cm = None
    try:
        weight_kg = float(data.get("weight_kg") or 0) or None
    except:
        weight_kg = None

    birth_date = None
    bd = data.get("birth_date")
    if bd:
        try:
            birth_date = datetime.strptime(bd, "%Y-%m-%d").date()
        except:
            birth_date = None

    sex = data.get("sex") if data.get("sex") in ("male","female","other") else user.sex
    activity_multiplier = None
    try:
        activity_multiplier = float(data.get("activity_multiplier"))
    except:
        activity_multiplier = user.activity_multiplier

    goal = data.get("goal") if data.get("goal") in ("maintain","lose","gain") else user.goal

    user.height_cm = height_cm
    user.weight_kg = weight_kg
    user.birth_date = birth_date or user.birth_date
    user.sex = sex
    user.activity_multiplier = activity_multiplier
    user.goal = goal
    try:
        model_pred = predict_target_from_model(user)
        if model_pred:
            user.target_calories = float(model_pred)
        else:
            bmr = compute_bmr(user)
            if user.activity_multiplier:
                t = bmr * user.activity_multiplier
            else:
                t = bmr * 1.3
            if user.goal == "lose":
                t = t - 300
            elif user.goal == "gain":
                t = t + 300
            user.target_calories = max(1000, t)
    except Exception as exc:
        current_app.logger.exception("Error predicting target calories")
        bmr = compute_bmr(user)
        user.target_calories = bmr * (user.activity_multiplier or 1.3)

    try:
        db.session.add(user)
        db.session.commit()
        flash("Profile updated", "success")
    except Exception as exc:
        db.session.rollback()
        flash("Failed to update profile", "danger")
    return redirect(url_for("profile.profile"))
