"""
routes_auth.py
Registration, login, logout and profile pages.
"""
import sqlite3
import time
from datetime import date

from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import (EXAM_CATEGORIES, INDIAN_STATES, QUALIFICATION_LABEL_TO_LEVEL,
                    QUALIFICATION_LEVELS)
from utils import (calculate_age, endpoint_url, is_safe_next_url, is_valid_email,
                   login_required, parse_date, password_error)

# --- Simple brute-force protection (kept in memory) -------------------
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 5 * 60
_failed_logins = {}   # key -> {"count": int, "locked_until": float}

# Used so that a wrong email takes as long to check as a wrong password.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _is_locked(key):
    entry = _failed_logins.get(key)
    return bool(entry and entry["locked_until"] > time.time())


def _record_failure(key):
    entry = _failed_logins.setdefault(key, {"count": 0, "locked_until": 0})
    entry["count"] += 1
    if entry["count"] >= MAX_FAILED_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCK_SECONDS
        entry["count"] = 0


def _form_options():
    """Dropdown values needed by register.html and profile.html."""
    return {
        "states": INDIAN_STATES,
        "qualifications": list(QUALIFICATION_LEVELS.values()),
        "categories": EXAM_CATEGORIES,
    }


def validate_profile_fields(form):
    """
    Shared by registration and profile update.
    Returns (clean_data, errors). errors is empty when everything is valid.
    """
    data = {
        "full_name": " ".join(form.get("full_name", "").split()),
        "date_of_birth": form.get("date_of_birth", "").strip(),
        "highest_qualification": form.get("highest_qualification", "").strip(),
        "state": form.get("state", "").strip(),
        "district": " ".join(form.get("district", "").split()),
        "preferred_category": form.get("preferred_category", "").strip(),
    }
    errors = {}

    name = data["full_name"]
    if not 2 <= len(name) <= 100:
        errors["full_name"] = "Full name must be 2 to 100 characters."
    elif not all(ch.isalpha() or ch in " .'-" for ch in name):
        errors["full_name"] = "Name may contain only letters, spaces, dots, hyphens and apostrophes."

    dob = parse_date(data["date_of_birth"])
    if dob is None:
        errors["date_of_birth"] = "Please enter a valid date of birth."
    elif dob > date.today():
        errors["date_of_birth"] = "Date of birth cannot be in the future."
    else:
        age = calculate_age(dob)
        if age < 14 or age > 70:
            errors["date_of_birth"] = "Age must be between 14 and 70 years."

    if data["highest_qualification"] not in QUALIFICATION_LABEL_TO_LEVEL:
        errors["highest_qualification"] = "Please select your highest qualification."

    if data["state"] not in INDIAN_STATES:
        errors["state"] = "Please select your state."

    if not 2 <= len(data["district"]) <= 60:
        errors["district"] = "District must be 2 to 60 characters."

    if data["preferred_category"] and data["preferred_category"] not in EXAM_CATEGORIES:
        errors["preferred_category"] = "Please choose a valid category."

    return data, errors


def register_routes(app):

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------
    @app.route("/register", methods=["GET", "POST"], endpoint="register")
    def register_user():
        if g.user:
            return redirect(endpoint_url("dashboard"))

        if request.method == "GET":
            return render_template("register.html", form={}, errors={}, **_form_options())

        data, errors = validate_profile_fields(request.form)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        data["email"] = email

        if not is_valid_email(email):
            errors["email"] = "Please enter a valid email address."
        elif db.get_user_by_email(email):
            errors["email"] = "An account with this email already exists."

        problem = password_error(password)
        if problem:
            errors["password"] = problem
        elif password != confirm:
            errors["confirm_password"] = "Passwords do not match."

        if errors:
            flash("Please correct the highlighted fields.", "danger")
            return render_template("register.html", form=data, errors=errors, **_form_options())

        try:
            db.create_user(
                full_name=data["full_name"], email=email,
                password_hash=generate_password_hash(password),
                date_of_birth=data["date_of_birth"],
                highest_qualification=data["highest_qualification"],
                state=data["state"], district=data["district"],
                preferred_category=data["preferred_category"] or None,
                role="user",        # always 'user'; admins are made with create_admin.py
            )
        except sqlite3.IntegrityError:
            errors["email"] = "An account with this email already exists."
            return render_template("register.html", form=data, errors=errors, **_form_options())

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"], endpoint="login")
    def login_user():
        if g.user:
            return redirect(endpoint_url("dashboard"))

        next_url = request.values.get("next", "")

        if request.method == "GET":
            return render_template("login.html", email="", next_url=next_url)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        key = f"{request.remote_addr}|{email}"

        if _is_locked(key):
            flash("Too many failed attempts. Please wait 5 minutes and try again.", "danger")
            return render_template("login.html", email=email, next_url=next_url), 429

        user = db.get_user_by_email(email) if email else None
        password_ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)

        if user is None or not password_ok:
            _record_failure(key)
            flash("Invalid email or password.", "danger")
            return render_template("login.html", email=email, next_url=next_url)

        _failed_logins.pop(key, None)
        session.clear()                       # start a fresh session (prevents session fixation)
        session["user_id"] = user["id"]
        session.permanent = True
        flash(f"Welcome back, {user['full_name']}!", "success")

        if is_safe_next_url(next_url):
            return redirect(next_url)
        return redirect(endpoint_url("dashboard"))

    # ------------------------------------------------------------------
    # Logout (POST only, protected by CSRF)
    # ------------------------------------------------------------------
    @app.route("/logout", methods=["POST"], endpoint="logout")
    def logout_user():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # Profile (update details / change password)
    # ------------------------------------------------------------------
    @app.route("/profile", methods=["GET", "POST"], endpoint="profile")
    @login_required
    def profile_page():
        if request.method == "GET":
            return render_template("profile.html", form=dict(g.user), errors={},
                                   pw_errors={}, **_form_options())

        action = request.form.get("action", "update_profile")

        # ---- Change password ----
        if action == "change_password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_new_password", "")
            pw_errors = {}

            if not check_password_hash(g.user["password_hash"], current):
                pw_errors["current_password"] = "Current password is incorrect."
            problem = password_error(new)
            if problem:
                pw_errors["new_password"] = problem
            elif new != confirm:
                pw_errors["confirm_new_password"] = "New passwords do not match."

            if pw_errors:
                flash("Password was not changed. Please fix the errors.", "danger")
                return render_template("profile.html", form=dict(g.user), errors={},
                                       pw_errors=pw_errors, **_form_options())

            db.execute_db("UPDATE users SET password_hash = ? WHERE id = ?",
                          (generate_password_hash(new), g.user["id"]))
            flash("Password changed successfully.", "success")
            return redirect(url_for("profile"))

        # ---- Update profile details ----
        data, errors = validate_profile_fields(request.form)
        if errors:
            data["email"] = g.user["email"]
            flash("Please correct the highlighted fields.", "danger")
            return render_template("profile.html", form=data, errors=errors,
                                   pw_errors={}, **_form_options())

        db.execute_db(
            """UPDATE users SET full_name = ?, date_of_birth = ?, highest_qualification = ?,
                                state = ?, district = ?, preferred_category = ?
               WHERE id = ?""",
            (data["full_name"], data["date_of_birth"], data["highest_qualification"],
             data["state"], data["district"], data["preferred_category"] or None, g.user["id"]))
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))