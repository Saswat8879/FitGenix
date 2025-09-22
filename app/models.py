from datetime import datetime
from .extensions import db

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=True)
    full_name = db.Column(db.String(255))
    sex = db.Column(db.Enum('male','female','other', name='sex_enum'), default='male')
    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    birth_date = db.Column(db.Date)
    activity_multiplier = db.Column(db.Float, default=None, nullable=True)
    activity_level = db.Column(db.String(50), default=None, nullable=True)
    google_tokens = db.Column(db.Text, default=None, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def display_name(self):
        return self.full_name or (self.email.split("@")[0] if self.email else "User")

class Meal(db.Model):
    __tablename__ = "meals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time)
    name = db.Column(db.String(255), nullable=False)
    calories = db.Column(db.Float, default=0.0)
    protein_g = db.Column(db.Float, default=0.0)
    carbs_g = db.Column(db.Float, default=0.0)
    fat_g = db.Column(db.Float, default=0.0)
    flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def kcal(self):
        try:
            return float(self.calories or 0.0)
        except Exception:
            return 0.0

    @property
    def logged_at(self):
        try:
            if self.time:
                return self.time
            if self.created_at:
                return self.created_at.time()
        except Exception:
            pass
        return None

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "time": self.time.isoformat() if self.time else None,
            "logged_at": (self.logged_at.isoformat() if self.logged_at else None),
            "name": self.name,
            "calories": float(self.calories or 0.0),
            "kcal": float(self.calories or 0.0),
            "protein_g": float(self.protein_g or 0.0),
            "carbs_g": float(self.carbs_g or 0.0),
            "fat_g": float(self.fat_g or 0.0),
            "flagged": bool(self.flagged),
            "flag_reason": self.flag_reason
        }

class Activity(db.Model):
    __tablename__ = "activities"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time, nullable=False)
    activity_type = db.Column(db.String(128), nullable=False)
    duration_minutes = db.Column(db.Float, nullable=True)
    calories_burned = db.Column(db.Float, nullable=True)
    notes = db.Column(db.String(1024), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "time": self.time.isoformat() if self.time else None,
            "activity_type": self.activity_type,
            "duration_minutes": float(self.duration_minutes) if self.duration_minutes is not None else None,
            "calories_burned": float(self.calories_burned) if self.calories_burned is not None else None,
            "notes": self.notes
        }

class FitnessData(db.Model):
    __tablename__ = "fitness_data"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    calories_burned = db.Column(db.Float, default=0.0)
    avg_bpm = db.Column(db.Float, default=None, nullable=True)
    sleep_hours = db.Column(db.Float, default=None, nullable=True)
    raw_payload = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "calories_burned": float(self.calories_burned or 0.0),
            "avg_bpm": float(self.avg_bpm) if self.avg_bpm is not None else None,
            "sleep_hours": float(self.sleep_hours) if self.sleep_hours is not None else None,
        }

class LifestylePoint(db.Model):
    __tablename__ = "lifestyle_points"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    points = db.Column(db.Float, default=0.0)
    reason = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "points": float(self.points or 0.0),
            "reason": self.reason
        }
