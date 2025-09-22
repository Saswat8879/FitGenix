from flask import Blueprint, request, render_template, redirect, url_for, flash, current_app
from .extensions import db
from .models import Activity, FitnessData, LifestylePoint
from .utils import login_required, get_current_user
from datetime import datetime, date
from sqlalchemy import func

activities_bp = Blueprint("activities", __name__, template_folder="templates")

def _server_now():
    now = datetime.now()
    return now.date(), now.time()

def compute_lifestyle_points_for_user_date(user_id, target_date):
    points = 0.0
    reasons = []
    activities = Activity.query.filter_by(user_id=user_id, date=target_date).all()
    total_activity_minutes = 0.0
    total_activity_calories = 0.0
    for a in activities:
        try:
            if a.duration_minutes:
                total_activity_minutes += float(a.duration_minutes)
            if a.calories_burned:
                total_activity_calories += float(a.calories_burned)
        except Exception:
            continue
    activity_points = (total_activity_minutes / 30.0) * 10.0 + (total_activity_calories / 100.0) * 2.0
    if activity_points:
        points += activity_points
        reasons.append(f"activity:{activity_points:.1f}")
    fd = FitnessData.query.filter_by(user_id=user_id, date=target_date).first()
    if fd:
        if fd.avg_bpm is not None:
            try:
                bpm = float(fd.avg_bpm)
                bpm_pts = 0.0
                if 60 <= bpm < 90:
                    bpm_pts = 2.0
                elif 90 <= bpm < 110:
                    bpm_pts = 6.0
                elif bpm >= 110:
                    bpm_pts = 3.0
                points += bpm_pts
                reasons.append(f"bpm:{bpm_pts:.1f}")
            except Exception:
                pass
        if fd.sleep_hours is not None:
            try:
                sh = float(fd.sleep_hours)
                sleep_pts = 0.0
                if 7.0 <= sh <= 9.0:
                    sleep_pts = 20.0
                elif 6.0 <= sh < 7.0 or 9.0 < sh <= 10.0:
                    sleep_pts = 10.0
                else:
                    sleep_pts = 0.0
                points += sleep_pts
                reasons.append(f"sleep:{sleep_pts:.1f}")
            except Exception:
                pass
        if fd.calories_burned:
            try:
                cal = float(fd.calories_burned)
                fd_cal_pts = (cal / 200.0) * 2.0
                points += fd_cal_pts
                reasons.append(f"fitcal:{fd_cal_pts:.1f}")
            except Exception:
                pass
    points = round(points, 1)
    reason_text = ", ".join(reasons) if reasons else None
    lp = LifestylePoint.query.filter_by(user_id=user_id, date=target_date).first()
    if not lp:
        lp = LifestylePoint(user_id=user_id, date=target_date, points=points, reason=reason_text)
        db.session.add(lp)
    else:
        lp.points = points
        lp.reason = reason_text
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to commit LifestylePoint upsert")

    return points

@activities_bp.route("/", methods=["GET"])
@login_required
def index():
    user = get_current_user()
    today = date.today()
    activities = Activity.query.filter_by(user_id=user.id, date=today).order_by(Activity.time.desc()).all()
    manual_burn = sum((a.calories_burned or 0.0) for a in activities)
    fd = FitnessData.query.filter_by(user_id=user.id, date=today).first()
    fit_burn = fd.calories_burned if fd else 0.0
    lp = LifestylePoint.query.filter_by(user_id=user.id, date=today).first()
    today_points = lp.points if lp else 0.0

    return render_template("activities.html",
                           activities=activities,
                           today=today,
                           manual_burn=manual_burn,
                           fit_burn=fit_burn,
                           today_points=today_points)

@activities_bp.route("/add", methods=["POST"])
@login_required
def add_activity():
    user = get_current_user()
    activity_type = (request.form.get("activity_type") or "").strip()
    duration = request.form.get("duration_minutes")
    calories = request.form.get("calories_burned")
    notes = request.form.get("notes") or None

    bpm = request.form.get("avg_bpm")
    sleep_hours = request.form.get("sleep_hours")

    if not activity_type and not bpm and not sleep_hours:
        flash("Please provide an activity or bpm or sleep hours.", "warning")
        return redirect(url_for("activities.index"))

    now_date, now_time = _server_now()
    if activity_type:
        try:
            duration_val = float(duration) if duration else None
        except Exception:
            duration_val = None
        try:
            cal_val = float(calories) if calories else None
        except Exception:
            cal_val = None

        a = Activity(
            user_id=user.id,
            date=now_date,
            time=now_time,
            activity_type=activity_type,
            duration_minutes=duration_val,
            calories_burned=cal_val,
            notes=notes
        )
        try:
            db.session.add(a)
            db.session.commit()
            flash("Activity logged.", "success")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to save Activity")
            flash("Failed to save activity (server error).", "danger")
    fd = FitnessData.query.filter_by(user_id=user.id, date=now_date).first()
    created_fd = False
    if not fd:
        fd = FitnessData(user_id=user.id, date=now_date, calories_burned=0.0)
        created_fd = True

    updated = False
    if bpm:
        try:
            fd.avg_bpm = float(bpm)
            updated = True
        except Exception:
            current_app.logger.debug("Invalid bpm input: %s", bpm)

    if sleep_hours:
        try:
            fd.sleep_hours = float(sleep_hours)
            updated = True
        except Exception:
            current_app.logger.debug("Invalid sleep input: %s", sleep_hours)
    if request.form.get("fd_calories"):
        try:
            fd.calories_burned = float(request.form.get("fd_calories"))
            updated = True
        except Exception:
            current_app.logger.debug("Invalid fd_calories input")

    try:
        if created_fd:
            db.session.add(fd)
        if updated or created_fd:
            db.session.commit()
            flash("Fitness summary updated.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to upsert FitnessData")
    try:
        compute_lifestyle_points_for_user_date(user.id, now_date)
    except Exception:
        current_app.logger.exception("Failed to compute lifestyle points (non-fatal)")

    return redirect(url_for("activities.index"))

@activities_bp.route("/delete/<int:activity_id>", methods=["POST"])
@login_required
def delete_activity(activity_id):
    user = get_current_user()
    a = Activity.query.get(activity_id)
    if not a or a.user_id != user.id:
        flash("Activity not found.", "warning")
        return redirect(url_for("activities.index"))
    try:
        date_of = a.date
        db.session.delete(a)
        db.session.commit()
        flash("Activity removed.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to delete activity")
        flash("Failed to delete activity.", "danger")
    try:
        compute_lifestyle_points_for_user_date(user.id, date_of)
    except Exception:
        current_app.logger.exception("Failed to recompute lifestyle points after deletion")

    return redirect(url_for("activities.index"))
