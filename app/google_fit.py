import os
import json
import time
import traceback
from functools import wraps

import requests
from flask import (
    Blueprint, current_app, request, session, redirect, url_for,
    jsonify, make_response, flash
)
from google_auth_oauthlib.flow import Flow

google_fit_bp = Blueprint("google_fit", __name__, template_folder="templates")

_DEFAULT_SCOPE_STR = os.environ.get(
    "GOOGLE_FIT_SCOPES",
    "https://www.googleapis.com/auth/fitness.activity.read "
    "https://www.googleapis.com/auth/fitness.heart_rate.read "
    "https://www.googleapis.com/auth/fitness.sleep.read "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/userinfo.email openid profile email"
)
DEFAULT_SCOPES = _DEFAULT_SCOPE_STR.split()

def _get_client_config():
    cfg_json = current_app.config.get("GOOGLE_OAUTH_CLIENT_CONFIG_JSON") or os.environ.get("GOOGLE_OAUTH_CLIENT_CONFIG_JSON")
    if cfg_json:
        try:
            return json.loads(cfg_json)
        except Exception:
            current_app.logger.exception("Failed to parse GOOGLE_OAUTH_CLIENT_CONFIG_JSON")

    client_id = current_app.config.get("GOOGLE_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET") or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")

    if client_id and client_secret and redirect_uri:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

    current_app.logger.warning("Google OAuth client config not found")
    return None

def _persist_tokens_if_possible(token_blob):
    saved = {"session": False, "db": False}
    try:
        session["google_oauth_credentials"] = token_blob
        saved["session"] = True
    except Exception:
        current_app.logger.exception("Failed to save google tokens to session")

    user_id = session.get("user_id")
    if user_id:
        try:
            from .extensions import db as _db
            from .models import User as _User
            u = _User.query.get(user_id)
            if u:
                try:
                    setattr(u, "google_tokens", json.dumps(token_blob))
                    _db.session.add(u)
                    _db.session.commit()
                    saved["db"] = True
                except Exception:
                    current_app.logger.exception("Failed to persist google tokens to DB (non-fatal)")
        except Exception:
            current_app.logger.debug("DB persistence not available or failed (skipping)")

    return saved

def _make_flow(client_config):
    redirect_uri = client_config["web"]["redirect_uris"][0]
    return Flow.from_client_config(client_config=client_config, scopes=DEFAULT_SCOPES, redirect_uri=redirect_uri)

def dev_only(f):
    @wraps(f)
    def wrapped(*a, **kw):
        return f(*a, **kw)
    return wrapped


@google_fit_bp.route("/connect")
def connect():
    return redirect(url_for("google_fit.authorize"))

@google_fit_bp.route("/authorize")
def authorize():
    client_config = _get_client_config()
    if not client_config:
        return jsonify({"error": "google_oauth_not_configured"}), 500

    flow = _make_flow(client_config)
    auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    session["google_oauth_state"] = state
    current_app.logger.info("google_authorize: saved google_oauth_state in session; state=%s", state)
    return redirect(auth_url)

def _attempt_manual_token_exchange(client_config, redirect_uri, code):
    try:
        token_uri = client_config["web"]["token_uri"]
        payload = {
            "code": code,
            "client_id": client_config["web"]["client_id"],
            "client_secret": client_config["web"]["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        r = requests.post(token_uri, data=payload, timeout=10)
        current_app.logger.info("Manual token endpoint HTTP %s body=%s", r.status_code, r.text)
        try:
            return r.json()
        except Exception:
            return {"body": r.text}
    except Exception as me:
        current_app.logger.exception("Manual token endpoint request failed")
        return {"error": str(me)}

def _build_creds_from_manual(manual_result):
    return {
        "token": manual_result.get("access_token"),
        "refresh_token": manual_result.get("refresh_token"),
        "token_type": manual_result.get("token_type"),
        "expires_in": manual_result.get("expires_in"),
        "scope": manual_result.get("scope"),
        "obtained_at": time.time()
    }

@google_fit_bp.route("/callback")
def callback():
    current_app.logger.info("Google callback invoked. full_url=%s query=%s", request.url, request.args.to_dict())

    client_config = _get_client_config()
    if not client_config:
        return jsonify({"error": "google_oauth_not_configured"}), 500

    req_state = request.args.get("state")
    saved_state = session.get("google_oauth_state")
    current_app.logger.info("google_callback: request_state=%s saved_state=%s session_keys=%s",
                            req_state, saved_state, list(session.keys()))

    redirect_uri = client_config["web"]["redirect_uris"][0]
    flow = _make_flow(client_config)
    if not saved_state:
        msg = ("Missing saved state in session. Possible causes: SECRET_KEY not set, "
               "SESSION_COOKIE_SECURE True on http, cookies blocked, or server restarted.")
        current_app.logger.warning(msg)
        code = request.args.get("code")
        if code:
            manual_result = _attempt_manual_token_exchange(client_config, redirect_uri, code)
            if isinstance(manual_result, dict) and manual_result.get("access_token"):
                creds = _build_creds_from_manual(manual_result)
                saved = _persist_tokens_if_possible(creds)
                flash("Connected Google Fit (session was missing state; tokens saved).", "success")
                current_app.logger.info("google_callback: manual tokens saved (missing saved_state): %s", saved)
                return redirect(url_for("index"))
        return jsonify({
            "error": "missing_saved_state",
            "message": msg,
            "request_state": req_state,
            "session_keys": list(session.keys())
        }), 400
    if req_state != saved_state:
        current_app.logger.error("google_callback: mismatching state (possible CSRF or session lost) req=%s saved=%s", req_state, saved_state)
        code = request.args.get("code")
        manual_result = None
        if code:
            manual_result = _attempt_manual_token_exchange(client_config, redirect_uri, code)

        if isinstance(manual_result, dict) and manual_result.get("access_token"):
            creds = _build_creds_from_manual(manual_result)
            saved = _persist_tokens_if_possible(creds)
            flash("Connected Google Fit (state mismatch resolved by manual exchange).", "success")
            current_app.logger.info("google_callback: manual token exchange succeeded; saved=%s", saved)
            return redirect(url_for("index"))

        return jsonify({
            "error": "mismatching_state",
            "message": "State value in callback does not match the one saved in session.",
            "request_state": req_state,
            "saved_state": saved_state,
            "manual_token_result": manual_result
        }), 400
    code = request.args.get("code")
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        token_info = {
            "token": credentials.token,
            "refresh_token": getattr(credentials, "refresh_token", None),
            "token_uri": getattr(credentials, "token_uri", None),
            "client_id": getattr(credentials, "client_id", None),
            "scopes": getattr(credentials, "scopes", None),
            "expiry": getattr(credentials, "expiry", None).timestamp() if getattr(credentials, "expiry", None) else None,
            "obtained_at": time.time()
        }
        saved = _persist_tokens_if_possible(token_info)
        current_app.logger.info("google_callback: token exchange successful; saved=%s", saved)
        flash("Connected Google Fit.", "success")
        return redirect(url_for("index"))
    except Exception as e:
        current_app.logger.exception("google oauth token exchange failed (fetch_token); attempting manual fallback")
        current_app.logger.debug("fetch_token exception: %s", str(e))
        if code:
            manual_result = _attempt_manual_token_exchange(client_config, redirect_uri, code)
            if isinstance(manual_result, dict) and manual_result.get("access_token"):
                creds = _build_creds_from_manual(manual_result)
                saved = _persist_tokens_if_possible(creds)
                flash("Connected Google Fit (manual token exchange after fetch_token failure).", "success")
                current_app.logger.info("google_callback: manual token exchange succeeded after fetch_token error; saved=%s", saved)
                return redirect(url_for("index"))
            else:
                current_app.logger.error("Manual token exchange after fetch_token failure did not return tokens: %s", manual_result)
                return make_response(jsonify({
                    "error": "google_oauth_token_exchange_failed",
                    "message": "fetch_token failed and manual exchange did not return tokens.",
                    "fetch_exception": str(e),
                    "manual_result": manual_result,
                    "details": {
                        "request_args": request.args.to_dict(),
                        "session_keys": list(session.keys()),
                        "session_google_oauth_state": saved_state
                    },
                    "traceback": traceback.format_exc()
                }), 500)
        else:
            return make_response(jsonify({
                "error": "google_oauth_token_exchange_failed",
                "message": "fetch_token failed and no authorization code present for manual retry.",
                "fetch_exception": str(e),
                "details": {
                    "request_args": request.args.to_dict(),
                    "session_keys": list(session.keys()),
                    "session_google_oauth_state": saved_state
                },
                "traceback": traceback.format_exc()
            }), 500)

@google_fit_bp.route("/refresh")
def refresh_token():
    credentials = session.get("google_oauth_credentials")
    refresh_token = credentials.get("refresh_token") if credentials else None

    if not refresh_token:
        user_id = session.get("user_id")
        if user_id:
            try:
                from .models import User as _User
                u = _User.query.get(user_id)
                val = getattr(u, "google_tokens", None)
                if val:
                    try:
                        parsed = json.loads(val)
                        refresh_token = parsed.get("refresh_token")
                    except Exception:
                        pass
            except Exception:
                current_app.logger.debug("DB not available for refresh lookup")

    if not refresh_token:
        return jsonify({"error": "no_refresh_token", "message": "No refresh_token found in session or DB"}), 400

    client_config = _get_client_config()
    if not client_config:
        return jsonify({"error": "google_oauth_not_configured"}), 500

    try:
        token_uri = client_config["web"]["token_uri"]
        payload = {
            "client_id": client_config["web"]["client_id"],
            "client_secret": client_config["web"]["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        r = requests.post(token_uri, data=payload, timeout=10)
        current_app.logger.info("Refresh token endpoint HTTP %s body=%s", r.status_code, r.text)
        if r.status_code == 200:
            resp = r.json()
            creds = session.get("google_oauth_credentials") or {}
            creds.update({
                "token": resp.get("access_token"),
                "expires_in": resp.get("expires_in"),
                "obtained_at": time.time()
            })
            if resp.get("refresh_token"):
                creds["refresh_token"] = resp.get("refresh_token")
            _persist_tokens_if_possible(creds)
            return jsonify({"status": "ok", "new_tokens": resp}), 200
        else:
            return jsonify({"error": "refresh_failed", "response": r.text}), 400
    except Exception:
        current_app.logger.exception("Exception during token refresh")
        return jsonify({"error": "refresh_exception", "trace": traceback.format_exc()}), 500

@google_fit_bp.route("/status")
def status():
    creds = session.get("google_oauth_credentials")
    connected = bool(creds and creds.get("token"))
    info = {
        "connected": connected,
        "in_session": bool(creds),
        "session_keys": list(session.keys())
    }
    try:
        user_id = session.get("user_id")
        if user_id:
            from .models import User as _User
            u = _User.query.get(user_id)
            if u:
                info["db_tokens_present"] = bool(getattr(u, "google_tokens", None))
    except Exception:
        current_app.logger.debug("User/DB not available for status info")
    return jsonify(info), 200

@google_fit_bp.route("/debug/tokens")
@dev_only
def debug_tokens():
    return jsonify({
        "session_tokens": session.get("google_oauth_credentials"),
        "session_keys": list(session.keys())
    }), 200
