from app.nutrition import compute_flags_for_meal
from app.models import Meal

def make_meal(cals, prot=0, carbs=0, fat=0):
    m = Meal(name="test", calories=cals, protein_g=prot, carbs_g=carbs, fat_g=fat, date=None, user_id=1)
    return m

def test_high_cal_flag():
    m = make_meal(900, prot=10, carbs=50, fat=40)
    f, reason = compute_flags_for_meal(m)
    assert f
    assert "Very high calorie" in reason

def test_balanced_not_flagged():
    m = make_meal(450, prot=30, carbs=50, fat=10)
    f, reason = compute_flags_for_meal(m)
    assert not f
