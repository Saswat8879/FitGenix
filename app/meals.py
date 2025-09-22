import os
import time
import json
import requests
from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app, session
)
from .extensions import db
from .models import Meal, LifestylePoint, FitnessData
from .schemas import MealSchema
from .utils import login_required, get_current_user
from .nutrition import compute_flags_for_meal, compute_daily_targets, compute_lifestyle_points
from datetime import date, datetime, timezone
from marshmallow import ValidationError

meals_bp = Blueprint("meals", __name__, template_folder="templates")

CALORIE_NINJAS_KEY = os.environ.get("CALORIE_NINJAS_KEY") or os.environ.get("CALORIE_NINJAS_KEY".upper())
CALORIE_NINJAS_URL = "https://api.calorieninjas.com/v1/nutrition"

def lookup_calories_calorieninjas(query):
    """Query CalorieNinjas for calories. Return float or None."""
    if not CALORIE_NINJAS_KEY:
        current_app.logger.debug("CALORIE_NINJAS_KEY not set; skipping lookup")
        return None

    try:
        headers = {"X-Api-Key": CALORIE_NINJAS_KEY}
        params = {"query": query}
        resp = requests.get(CALORIE_NINJAS_URL, params=params, headers=headers, timeout=8)
        current_app.logger.debug("CalorieNinjas HTTP %s for query=%s", resp.status_code, query)
        if resp.status_code != 200:
            current_app.logger.warning("CalorieNinjas returned %s: %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        items = data.get("items") or []
        if not items:
            return None
        for item in items:
            c = item.get("calories")
            if c is not None:
                try:
                    return float(c)
                except Exception:
                    continue
        first = items[0]
        if "calories" in first:
            try:
                return float(first["calories"])
            except Exception:
                pass
        return None
    except Exception:
        current_app.logger.exception("CalorieNinjas lookup failed")
        return None

def _server_now():
    """
    Return server's current date and time objects suitable for DB storage.
    - date: local date (not timezone-converted)
    - time: local time (no timezone info)
    """
    now = datetime.now()
    return now.date(), now.time()

@meals_bp.route("/", methods=["GET"])
@login_required
def index():
    user = get_current_user()
    today = date.today()
    try:
        meals = Meal.query.filter_by(user_id=user.id, date=today).order_by(Meal.time.asc()).all()
    except Exception:
        current_app.logger.exception("Failed to query meals ordered by time; falling back to unordered list")
        meals = Meal.query.filter_by(user_id=user.id, date=today).all()

    consumed = 0.0
    for m in meals:
        try:
            consumed += float(getattr(m, "calories", None) or getattr(m, "kcal", 0.0) or 0.0)
        except Exception:
            current_app.logger.debug("Failed to parse meal calories for id=%s", getattr(m, "id", None))

    fd = FitnessData.query.filter_by(user_id=user.id, date=today).first()
    activity_burned = fd.calories_burned if fd else 0.0

    try:
        targets = compute_daily_targets(user) or {}
    except Exception:
        current_app.logger.exception("compute_daily_targets failed; using empty")
        targets = {}

    target_calories = None
    if isinstance(targets, dict):
        target_calories = targets.get("target") or targets.get("target_calories") or targets.get("calories") or None

    try:
        consumed_val = float(consumed or 0.0)
        if target_calories:
            remaining = float(target_calories) - consumed_val
            excess = max(0.0, consumed_val - float(target_calories))
        else:
            remaining = None
            excess = 0.0
    except Exception:
        remaining = None
        excess = 0.0

    targets_payload = {
        "target_calories": int(round(target_calories)) if target_calories else None,
        "consumed": int(round(consumed_val)),
        "excess": int(round(excess)),
        "remaining": (int(round(remaining)) if remaining is not None else None),
    }

    if isinstance(targets, dict):
        try:
            for k, v in targets.items():
                if k not in targets_payload:
                    targets_payload[k] = v
        except Exception:
            current_app.logger.debug("Failed to merge extra target keys")

    target = targets_payload.get("target") or targets_payload.get("target_calories")
    consumed_val = targets_payload.get("consumed")
    remaining_val = targets_payload.get("remaining")
    excess_val = targets_payload.get("excess")

    return render_template(
        "meals.html",
        meals=meals,
        targets=targets_payload,
        today=today,
        activity_burned=activity_burned,
        user=user,
        target=target,
        consumed=consumed_val,
        remaining=remaining_val,
        excess=excess_val
    )

@meals_bp.route("/add", methods=["POST"])
@login_required
def add_meal():
    user = get_current_user()
    incoming = request.get_json(silent=True) or request.form or {}

    name = (incoming.get("name") or incoming.get("title") or "").strip()
    if not name:
        flash("Please provide a meal name (e.g. '1 apple').", "warning")
        return redirect(url_for("meals.index"))
    meal_date, meal_time = _server_now()
    calories = None
    try:
        calories = lookup_calories_calorieninjas(name)
    except Exception:
        current_app.logger.exception("CalorieNinjas lookup raised (non-fatal)")
    if calories is None:
        try:
            calories = float(incoming.get("calories") or incoming.get("kcal") or 0.0)
        except Exception:
            calories = 0.0

    meal = Meal(
        user_id=user.id,
        name=name,
        calories=calories,
        protein_g=None,
        carbs_g=None,
        fat_g=None,
        date=meal_date,
        time=meal_time
    )
    try:
        db.session.add(meal)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save meal")
        flash("Failed to save meal (server error)", "danger")
        return redirect(url_for("meals.index"))
    try:
        compute_flags_for_meal(meal)
        compute_lifestyle_points(user)
    except Exception:
        current_app.logger.debug("Flag/lifestyle computation failed (non-fatal)")

    flash("Meal logged", "success")
    return redirect(url_for("meals.index"))
