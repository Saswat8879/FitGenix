# scripts/add_target_cal_column.py
import sys
import os
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

THIS_FILE = os.path.abspath(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(THIS_FILE), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app import create_app
    from app.extensions import db
    from app.models import User
    from app.nutrition import compute_daily_targets
except Exception as e:
    print("Failed to import app modules. Are you running this from the project root and is your virtualenv active?")
    print("Error:", e)
    sys.exit(1)

def column_exists(engine, table_name, col_name):
    try:
        res = engine.execute(text(f"PRAGMA table_info({table_name});")).fetchall()
        cols = [r[1] for r in res]
        return col_name in cols
    except Exception as exc:
        print("Error checking columns:", exc)
        return False

def add_column_sqlite(engine, table_name, col_def_sql):
    try:
        engine.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_def_sql};"))
        return True
    except OperationalError as e:
        print("OperationalError adding column:", e)
        return False
    except Exception as e:
        print("Error adding column:", e)
        return False

def populate_targets(app, session):
    users = session.query(User).all()
    print(f"Found {len(users)} users — computing and saving targets...")
    updated = 0
    for u in users:
        try:
            tgt = compute_daily_targets(u)
            if isinstance(tgt, dict):
                value = float(tgt.get("target") or tgt.get("target_calories") or tgt.get("calories") or 0)
            elif isinstance(tgt, (int, float)):
                value = float(tgt)
            else:
                value = 0.0
            if value and (getattr(u, "target_calories", None) != value):
                u.target_calories = float(value)
                session.add(u)
                updated += 1
        except Exception as e:
            app.logger.exception("Failed to compute target for user %s: %s", getattr(u, "id", None), e)
    try:
        session.commit()
    except Exception:
        session.rollback()
    print(f"Updated target_calories for {updated} users.")

def main():
    app = create_app()
    with app.app_context():
        engine = db.get_engine(app)
        if column_exists(engine, "users", "target_calories"):
            print("Column 'target_calories' already exists in users table.")
        else:
            print("Adding column 'target_calories' to users table...")
            ok = add_column_sqlite(engine, "users", "target_calories FLOAT")
            if not ok:
                print("Failed to add column automatically. You may need to add it manually via sqlite cli.")
                sys.exit(1)
            print("Column added successfully.")
        
        populate_targets(app, db.session)
        print("Done.")


if __name__ == "__main__":
    main()
