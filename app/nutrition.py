import os
import json
import pickle
from datetime import date
import requests

MODEL_PATH = os.path.join(os.getcwd(), "instance", "target_cal_model.pkl")
_model_cache = None

def load_target_model():
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            d = pickle.load(f)
        model = d.get("model") if isinstance(d, dict) else d
        _model_cache = model
        return model
    except Exception:
        return None

def predict_target_from_model(user):
    model = load_target_model()
    if not model:
        return None
    try:
        age = date.today().year - user.birth_date.year if getattr(user, "birth_date", None) else 30
    except Exception:
        age = 30
    sex = 1 if getattr(user, "sex", "male") == "male" else 0
    height_cm = float(getattr(user, "height_cm", 165) or 165)
    weight_kg = float(getattr(user, "weight_kg", 70) or 70)
    activity = float(getattr(user, "activity_multiplier", 1.3) or 1.3)
    goal_raw = getattr(user, "goal", "maintain")
    goal = 0
    if goal_raw == "lose":
        goal = -1
    elif goal_raw == "gain":
        goal = 1
    X = [[age, sex, height_cm, weight_kg, activity, goal]]
    try:
        pred = model.predict(X)
        return float(pred[0])
    except Exception:
        return None

def compute_bmr(user):
    try:
        weight = float(getattr(user, "weight_kg", 70) or 70)
        height = float(getattr(user, "height_cm", 170) or 170)
        age = date.today().year - user.birth_date.year if getattr(user, "birth_date", None) else 30
        sex = getattr(user, "sex", "male")
        if sex == "male":
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161
        return float(max(800, bmr))
    except Exception:
        return 1600.0

def _activity_multiplier_from_level(level):
    mapping = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9
    }
    return mapping.get(level, 1.2)

def compute_daily_targets(user):
    try:
        if getattr(user, "target_calories", None):
            return {"target": float(user.target_calories), "target_calories": float(user.target_calories)}
    except Exception:
        pass
    model_pred = predict_target_from_model(user)
    if model_pred:
        return {"target": model_pred, "target_calories": model_pred}
    bmr = compute_bmr(user)
    multiplier = getattr(user, "activity_multiplier", None) or _activity_multiplier_from_level(getattr(user, "activity_level", "sedentary"))
    try:
        multiplier = float(multiplier)
    except Exception:
        multiplier = 1.3
    target = bmr * multiplier
    goal = getattr(user, "goal", "maintain")
    if goal == "lose":
        target -= 300
    elif goal == "gain":
        target += 300
    target = max(1000, min(4500, target))
    return {"target": target, "target_calories": target}

def lookup_nutrition_text(text):
    if not text or not text.strip():
        return None
    text = text.strip()
    api_key = os.environ.get("CALORIE_NINJAS_KEY") or os.environ.get("API_NINJAS_KEY")
    if api_key:
        try:
            url = "https://api.calorieninjas.com/v1/nutrition"
            params = {"query": text}
            headers = {"X-Api-Key": api_key}
            r = requests.get(url, params=params, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                if items:
                    kcal = sum(float(i.get("calories", 0) or 0) for i in items)
                    prot = sum(float(i.get("protein_g", 0) or 0) for i in items)
                    carbs = sum(float(i.get("carbohydrates_total_g", 0) or 0) for i in items)
                    fat = sum(float(i.get("fat_total_g", 0) or 0) for i in items)
                    return {"kcal": kcal, "protein_g": prot, "carbs_g": carbs, "fat_g": fat, "source": "calorieninjas"}
        except Exception:
            pass

    ed_id = os.environ.get("EDAMAM_APP_ID")
    ed_key = os.environ.get("EDAMAM_APP_KEY")
    if ed_id and ed_key:
        try:
            url = "https://api.edamam.com/api/nutrition-data"
            params = {"app_id": ed_id, "app_key": ed_key, "ingr": text}
            r = requests.get(url, params=params, timeout=8)
            if r.status_code == 200:
                data = r.json()
                kcal = float(data.get("calories", 0) or 0)
                tot = data.get("totalNutrients", {}) or {}
                prot = float(tot.get("PROCNT", {}).get("quantity", 0) or 0)
                carbs = float(tot.get("CHOCDF", {}).get("quantity", 0) or 0)
                fat = float(tot.get("FAT", {}).get("quantity", 0) or 0)
                return {"kcal": kcal, "protein_g": prot, "carbs_g": carbs, "fat_g": fat, "source": "edamam"}
        except Exception:
            pass

    try:
        indb_path = os.path.join(os.getcwd(), "instance", "indian_nutrition.json")
        if os.path.exists(indb_path):
            with open(indb_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            key = text.lower()
            if key in db:
                rec = db[key]
                return {
                    "kcal": float(rec.get("energy_kcal", rec.get("kcal", 0) or 0)),
                    "protein_g": float(rec.get("protein_g", 0) or 0),
                    "carbs_g": float(rec.get("carbs_g", 0) or 0),
                    "fat_g": float(rec.get("fat_g", 0) or 0),
                    "source": "indian_db"
                }
    except Exception:
        pass

    return None

def compute_flags_for_meal(meal):
    try:
        name = (meal.name or "").strip()
        calories = float(getattr(meal, "calories", 0) or 0)
    except Exception:
        name = ""
        calories = 0.0

    if not name:
        return True, "Missing meal name"
    if calories <= 0:
        return True, "Calories missing or zero"
    if calories > 2000:
        return True, "Unusually high calories"
    return False, ""

def compute_lifestyle_points(calories_burned, sleep_hours, avg_meal_interval_hours, calories_intake, target_calories, avg_bpm):
    def score_range(val, low, mid, high):
        try:
            v = float(val)
        except Exception:
            return 0.0
        if v <= low or v >= high:
            return 0.0
        if v == mid:
            return 1.0
        if v < mid:
            return (v - low) / (mid - low)
        return (high - v) / (high - mid)

    burn_score = min(1.0, float(calories_burned or 0) / 400.0)
    sleep_score = score_range(sleep_hours or 0.0, 4.0, 7.5, 9.5)
    meal_interval_score = score_range(avg_meal_interval_hours or 3.5, 0.5, 3.5, 6.0)
    try:
        if not target_calories or target_calories <= 0:
            cal_ratio = 1.0
        else:
            cal_ratio = float((calories_intake or 0.0) / float(target_calories))
    except Exception:
        cal_ratio = 1.0
    cal_score = score_range(cal_ratio, 0.6, 1.0, 1.3)
    bpm_score = score_range(avg_bpm or 60, 40, 64, 86)
    total = (0.28 * burn_score + 0.25 * sleep_score + 0.18 * meal_interval_score + 0.20 * cal_score + 0.09 * bpm_score)
    points = round(total * 100, 2)
    return points
