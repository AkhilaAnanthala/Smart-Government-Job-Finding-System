"""
app.py
Creates and configures the Flask application.

Run the website with:   python app.py
"""
import importlib
import os
from urllib.parse import urlparse

from flask import Flask, flash, g, redirect, render_template, request, session
from flask_wtf.csrf import CSRFError, CSRFProtect

import db
from config import (Config, DIFFICULTY_LEVELS, EXAM_CATEGORIES, GOVT_CATEGORIES,
                    INDIAN_STATES, QUALIFICATION_LEVELS, RESOURCE_KINDS, RESOURCE_TYPES)
from utils import calculate_age, deadline_info, format_date, is_safe_next_url

csrf = CSRFProtect()

# Route files. Each one must define register_routes(app).
ROUTE_MODULES = [
    "routes_auth",
    "routes_public",
    "routes_jobs",
    "routes_prep",
    "routes_tests",
    "routes_admin",
]


def register_routes(app):
    """Load every route file that exists. Files not created yet are skipped."""
    for name in ROUTE_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as err:
            if err.name == name:  # only skip when the route file itself is missing
                print(f"[info] {name}.py not created yet - skipping")
                continue
            raise
        module.register_routes(app)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Make sure the tables exist (does nothing if they already do).
    conn = db.get_connection(app.config["DATABASE_PATH"])
    db.init_db(conn)
    conn.close()

    csrf.init_app(app)      # CSRF protection for every POST request
    db.init_app(app)        # close DB connection after each request

    # ---------------- Who is logged in? -----------------------------
    @app.before_request
    def load_logged_in_user():
        g.user = None
        if request.endpoint == "static":
            return
        user_id = session.get("user_id")
        if user_id is not None:
            user = db.get_user_by_id(user_id)
            if user is None:
                session.clear()      # account was deleted
            else:
                g.user = user        # role is re-read from the DB on every request

    # ---------------- Variables available in every template -------
    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "QUALIFICATION_LEVELS": QUALIFICATION_LEVELS,
            "EXAM_CATEGORIES": EXAM_CATEGORIES,
            "GOVT_CATEGORIES": GOVT_CATEGORIES,
            "INDIAN_STATES": INDIAN_STATES,
            "RESOURCE_TYPES": RESOURCE_TYPES,
            "RESOURCE_KINDS": RESOURCE_KINDS,
            "DIFFICULTY_LEVELS": DIFFICULTY_LEVELS,
            "deadline_info": deadline_info,
            "calculate_age": calculate_age,
        }

    app.add_template_filter(format_date, "format_date")

    # ---------------- Security headers --------------------------------
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if g.get("user") is not None:
            # Stops the browser back button from showing private pages after logout.
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---------------- Error pages --------------------------------------
    def back_or_home():
        target = request.referrer
        if target and is_safe_next_url(target):
            parts = urlparse(target)
            return parts.path + (f"?{parts.query}" if parts.query else "")
        return "/"

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        flash("Your session expired or the form was invalid. Please try again.", "danger")
        return redirect(back_or_home())

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def file_too_large(error):
        flash("That file is too large. The maximum upload size is 5 MB.", "danger")
        return redirect(back_or_home())

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500

    register_routes(app)
    return app


app = create_app()

if __name__ == "__main__":
    # 127.0.0.1 = only your own laptop can open the site.
    app.run(host="127.0.0.1", port=5000, debug=Config.DEBUG)