import numpy as np
import pandas as pd
import os
import pickle
from pathlib import Path
try:
    import xgboost as xgb
    has_xgb = True
except Exception:
    has_xgb = False
    from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor

def generate_synthetic(n=20000, seed=42):
    np.random.seed(seed)
    ages = np.random.randint(18, 70, size=n)
    sex = np.random.binomial(1, 0.5, size=n)
    heights = np.random.normal(165, 10, size=n).clip(140,210)
    weights = np.random.normal(70, 15, size=n).clip(35,160)
    activity = np.random.choice([1.2,1.375,1.55,1.725,1.9], size=n, p=[0.25,0.35,0.25,0.1,0.05])
    goals = np.random.choice([0,-1,1], size=n, p=[0.65,0.2,0.15])
    bmr = 10 * weights + 6.25 * heights - 5 * ages + (5 * (1-sex) - 161 * (1 - sex))
    bmr = 10 * weights + 6.25 * heights - 5 * ages + np.where(sex==1, 5, -161)
    target = bmr * activity + goals * 300 + np.random.normal(0, 120, size=n)
    df = pd.DataFrame({
        "age": ages,
        "sex": sex,
        "height_cm": heights,
        "weight_kg": weights,
        "activity": activity,
        "goal": goals,
        "target": target
    })
    return df

def train_and_save(path="instance/target_cal_model.pkl"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = generate_synthetic(50000)
    X = df[["age","sex","height_cm","weight_kg","activity","goal"]]
    y = df["target"]
    if has_xgb:
        model = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, verbosity=0)
    else:
        model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05)
    model.fit(X, y)
    with open(path, "wb") as f:
        pickle.dump({"model": model}, f)
    print("Saved model to", path)

if __name__ == "__main__":
    train_and_save()
