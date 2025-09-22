import os
import json
import pickle
import logging
from datetime import date
from pathlib import Path
from typing import Optional, Any, Dict

import requests
from requests.exceptions import RequestException, Timeout, HTTPError, ConnectionError, TooManyRedirects, SSLError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(os.getcwd(), "instance", "target_cal_model.pkl"))
MODEL_URL = os.environ.get("MODEL_URL", None)

# internal cache for loaded model
_model_cache: Optional[Any] = None

def _download_model_if_needed(model_url: str, model_path: str, timeout: int = 60) -> bool:
    """
    Download the model from model_url into model_path if it doesn't already exist.
    Returns True if model file exists after this call.
    """
    p = Path(model_path)
    if p.exists():
        logger.debug("Model already exists at %s", model_path)
        return True

    if not model_url:
        logger.debug("No MODEL_URL provided; not attempting download.")
        return False

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading model from %s to %s", model_url, model_path)
        with requests.Session() as s:
            r = s.get(model_url, timeout=timeout, stream=True)
            r.raise_for_status()
            # Write to temp file then move — avoids partial files on failure
            tmp_path = model_path + ".part"
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            Path(tmp_path).replace(p)
        logger.info("Model downloaded successfully to %s", model_path)
        return True
    except (RequestException, OSError) as e:
        logger.exception("Failed to download model from %s: %s", model_url, e)
        # clean up partial file if exists
        try:
            tmp = Path(model_path + ".part")
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def load_target_model() -> Optional[Any]:
    """
    Load the pickled model from disk (MODEL_PATH). If MODEL_URL is set and the file
    doesn't exist, attempt to download it first.
    Returns the raw model object or None on failure.
    """
    global _model_cache

    if _model_cache is not None:
        return _model_cache

    # If a remote MODEL_URL is provided, try to download it first (only if file missing)
    if MODEL_URL and not Path(MODEL_PATH).exists():
        _download_model_if_needed(MODEL_URL, MODEL_PATH)

    if not Path(MODEL_PATH).exists():
        logger.warning("Model file not found at %s", MODEL_PATH)
        return None

    try:
        with open(MODEL_PATH, "rb") as f:
            data = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, AttributeError, IndexError, Exception) as e:
        # Catch common pickle-related errors and log them
        logger.exception("Failed to unpickle model at %s: %s", MODEL_PATH, e)
        return None

    model = data.get("model") if isinstance(data, dict) else data
    _model_cache = model
    logger.info("Model loaded successfully from %s", MODEL_PATH)
    return model


def predict_target_from_model(user) -> Optional[float]:

    model = load_target_model()
    if model is None:
        return None

    try:
        age = date.today().year - user.birth_date.year if getattr(user, "birth_date", None) else 30
    except Exception:
        age = 30
    sex = 1 if getattr(user, "sex", "male") == "male" else 0
    try:
        height_cm = float(getattr(user, "height_cm", 165) or 165)
    except Exception:
        height_cm = 165.0
    try:
        weight_kg = float(getattr(user, "weight_kg", 70) or 70)
    except Exception:
        weight_kg = 70.0
    try:
        activity = float(getattr(user, "activity_multiplier", 1.3) or 1.3)
    except Exception:
        activity = 1.3

    goal_raw = getattr(user, "goal", "maintain")
    goal = 0
    if goal_raw == "lose":
        goal = -1
    elif goal_raw == "gain":
        goal = 1

    X = [[age, sex, height_cm, weight_kg, activity, goal]]

    predict_fn = getattr(model, "predict", None)
    if not callable(predict_fn):
        logger.warning("Loaded model at %s does not have a callable 'predict' method", MODEL_PATH)
        return None

    try:
        pred = predict_fn(X)
        # handle array-like outputs
        if hasattr(pred, "__iter__"):
            result = float(pred[0])
        else:
            result = float(pred)
        return result
    except Exception as e:
        logger.exception("Model prediction failed: %s", e)
        return None


def compute_bmr(user) -> float:
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
    except Exception as e:
        logger.exception("compute_bmr failed: %s", e)
        return 1600.0


def _activity_multiplier_from_level(level: str) -> float:
    mapping = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9
    }
    return mapping.get(level, 1.2)


def compute_daily_targets(user) -> Dict[str, float]:
    try:
        if getattr(user, "target_calories", None):
            val = float(user.target_calories)
            return {"target": val, "target_calories": val}
    except Exception:
        pass

    model_pred = predict_target_from_model(user)
    if model_pred:
        return {"target": model_pred, "target_calories": model_pred}

    bmr = compute_bmr(user)
    multiplier = getattr(user, "activity_multiplier", None) or _activity_multiplier_from_level(
        getattr(user, "activity_level", "sedentary"))
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


def lookup_nutrition_text(text: str) -> Optional[Dict[str, float]]:
    if not text or not text.strip():
        return None
    text = text.strip()
    api_key = os.environ.get("CALORIE_NINJAS_KEY") or os.environ.get("API_NINJAS_KEY")
    session = requests.Session()
    try:
        if api_key:
            try:
                url = "https://api.calorieninjas.com/v1/nutrition"
                params = {"query": text}
                headers = {"X-Api-Key": api_key}
                r = session.get(url, params=params, headers=headers, timeout=8)
                r.raise_for_status()
                data = r.json()
                items = data.get("items", [])
                if items:
                    kcal = sum(float(i.get("calories", 0) or 0) for i in items)
                    prot = sum(float(i.get("protein_g", 0) or 0) for i in items)
                    carbs = sum(float(i.get("carbohydrates_total_g", 0) or 0) for i in items)
                    fat = sum(float(i.get("fat_total_g", 0) or 0) for i in items)
                    return {"kcal": kcal, "protein_g": prot, "carbs_g": carbs, "fat_g": fat, "source": "calorieninjas"}
            except (RequestException, ValueError) as e:
                logger.debug("CalorieNinjas lookup failed for '%s': %s", text, e)

        ed_id = os.environ.get("EDAMAM_APP_ID")
        ed_key = os.environ.get("EDAMAM_APP_KEY")
        if ed_id and ed_key:
            try:
                url = "https://api.edamam.com/api/nutrition-data"
                params = {"app_id": ed_id, "app_key": ed_key, "ingr": text}
                r = session.get(url, params=params, timeout=8)
                r.raise_for_status()
                data = r.json()
                kcal = float(data.get("calories", 0) or 0)
                tot = data.get("totalNutrients", {}) or {}
                prot = float(tot.get("PROCNT", {}).get("quantity", 0) or 0)
                carbs = float(tot.get("CHOCDF", {}).get("quantity", 0) or 0)
                fat = float(tot.get("FAT", {}).get("quantity", 0) or 0)
                return {"kcal": kcal, "protein_g": prot, "carbs_g": carbs, "fat_g": fat, "source": "edamam"}
            except (RequestException, ValueError) as e:
                logger.debug("Edamam lookup failed for '%s': %s", text, e)

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
        except Exception as e:
            logger.debug("Local nutrition DB lookup failed for '%s': %s", text, e)

    finally:
        try:
            session.close()
        except Exception:
            pass

    return None


def compute_flags_for_meal(meal) -> (bool, str):
    try:
        name = (meal.name or "").strip()
        calories = float(getattr(meal, "calories", 0) or 0)
    except Exception as e:
        logger.debug("compute_flags_for_meal input parsing failed: %s", e)
        name = ""
        calories = 0.0

    if not name:
        return True, "Missing meal name"
    if calories <= 0:
        return True, "Calories missing or zero"
    if calories > 2000:
        return True, "Unusually high calories"
    return False, ""


def compute_lifestyle_points(calories_burned, sleep_hours, avg_meal_interval_hours, calories_intake, target_calories, avg_bpm) -> float:
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
