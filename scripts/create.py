# scripts/create_activities_table.py
from app import create_app
from app.extensions import db
from app.models import Activity

app = create_app()
with app.app_context():
    db.create_all()
    print("Created tables (if they didn't exist).")
