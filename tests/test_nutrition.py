from app.nutrition import compute_bmr, compute_daily_targets
from app.models import User
from datetime import date

def test_compute_targets_basic():
    u = User(weight_kg=70, height_cm=175, birth_date=date(1990,1,1), sex="male", activity_multiplier=1.2)
    bmr = compute_bmr(u)
    targets = compute_daily_targets(u)
    assert bmr > 1000
    assert targets["tdee"] > bmr
    assert targets["protein_g"] > 0
