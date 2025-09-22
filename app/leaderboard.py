from flask import Blueprint, render_template, request
from .models import User, LifestylePoint
from .utils import login_required, get_current_user
from datetime import date, timedelta
from sqlalchemy import func
from .extensions import db

leaderboard_bp = Blueprint("leaderboard", __name__, template_folder="templates")

@leaderboard_bp.route("/", methods=["GET"])
@login_required
def view_leaderboard():
    days = int(request.args.get("days", 7))
    date_to_str = request.args.get("date_to")
    if date_to_str:
        try:
            date_to = date.fromisoformat(date_to_str)
        except Exception:
            date_to = date.today()
    else:
        date_to = date.today()

    date_from = date_to - timedelta(days=days-1)
    rows = db.session.query(
        LifestylePoint.user_id,
        func.coalesce(func.sum(LifestylePoint.points), 0.0).label("total_points")
    ).filter(LifestylePoint.date >= date_from, LifestylePoint.date <= date_to).group_by(LifestylePoint.user_id).order_by(func.sum(LifestylePoint.points).desc()).limit(100).all()
    leaderboard = []
    for r in rows:
        user = User.query.get(r.user_id)
        leaderboard.append({
            "user_id": r.user_id,
            "display_name": user.display_name() if user else f"user:{r.user_id}",
            "total_points": float(r.total_points or 0.0)
        })

    return render_template("leaderboard.html", leaderboard=leaderboard, date_from=date_from, date_to=date_to, days=days)
