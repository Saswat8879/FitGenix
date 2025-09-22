import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///../instance/fitleaderboard.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")
    GOOGLE_FIT_SCOPES = os.environ.get("GOOGLE_FIT_SCOPES", "").split()
    DEFAULT_ACTIVITY_MULTIPLIER = float(os.environ.get("DEFAULT_ACTIVITY_MULTIPLIER", 1.2))