"""
utils.py
Small reusable helpers: access-control decorators, validation, date helpers
and safe file upload handling.
"""
import os
import re
import uuid
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, g, redirect, request, url_for
from werkzeug.utils import secure_filename

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# --------------------------------------------------------------------
# Access control decorators
# --------------------------------------------------------------------
def login_required(view):
    """Redirect to the login page if nobody is logged in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            next_page = request.full_path.rstrip("?") if request.method == "GET" else ""
            return redirect(url_for("login", next=next_page or None))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """Only users whose role is 'admin' may enter. Others get a 403 page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            next_page = request.full_path.rstrip("?") if request.method == "GET" else ""
            return redirect(url_for("login", next=next_page or None))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------
# Redirect helpers
# --------------------------------------------------------------------
def is_safe_next_url(target):
    """
    True only if the URL stays on this website. Prevents 'open redirect'
    attacks such as /login?next=https://evil.com
    """
    if not target:
        return False
    if "\\" in target or target.startswith("//"):
        return False
    parts = urlparse(target)
    if parts.scheme not in ("", "http", "https"):
        return False
    if parts.netloc and parts.netloc != request.host:
        return False
    return True


def endpoint_url(endpoint, fallback_path="/"):
    """
    url_for(endpoint) if that page exists yet, otherwise the fallback path.
    Lets the project run while later parts are still being added.
    """
    from flask import current_app as app
    if endpoint in app.view_functions:
        return url_for(endpoint)
    return fallback_path


# --------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------
def is_valid_email(email):
    return bool(email) and len(email) <= 254 and EMAIL_PATTERN.match(email) is not None


def password_error(password):
    """Return an error message if the password is weak, otherwise None."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password must be at most 128 characters long."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one number."
    return None


def is_valid_http_url(url):
    """Accept only http/https links with a host name (blocks javascript: links)."""
    if not url or len(url) > 500:
        return False
    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


# --------------------------------------------------------------------
# Date helpers
# --------------------------------------------------------------------
def parse_date(value):
    """Convert 'YYYY-MM-DD' text (or a date) into a date. Returns None if invalid."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_age(date_of_birth, on_date=None):
    """Age in completed years on a given date (default: today)."""
    dob = parse_date(date_of_birth)
    if dob is None:
        return None
    on_date = on_date or date.today()
    years = on_date.year - dob.year
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return years


def format_date(value):
    """Show 2026-11-05 as '05 Nov 2026'. Empty values become a dash."""
    parsed = parse_date(value)
    return parsed.strftime("%d %b %Y") if parsed else "-"


def deadline_info(deadline, today=None):
    """
    Describe an application deadline for badges in templates.
    Returns a dict: label, css_class (Bootstrap colour), days_left, is_open.
    """
    today = today or date.today()
    due = parse_date(deadline)
    if due is None:
        return {"label": "Deadline not announced", "css_class": "secondary",
                "days_left": None, "is_open": None}
    left = (due - today).days
    if left < 0:
        return {"label": "Closed", "css_class": "danger", "days_left": left, "is_open": False}
    if left == 0:
        return {"label": "Last day today", "css_class": "danger", "days_left": 0, "is_open": True}
    if left <= 7:
        return {"label": f"{left} days left", "css_class": "warning", "days_left": left, "is_open": True}
    return {"label": f"{left} days left", "css_class": "success", "days_left": left, "is_open": True}


# --------------------------------------------------------------------
# Safe PDF uploads
# --------------------------------------------------------------------
def allowed_file(filename):
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def upload_path(stored_name):
    """Full path of a stored upload. basename() blocks '../' tricks."""
    return os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(stored_name))


def save_pdf_upload(file_storage):
    """
    Validate and save an uploaded PDF.
    Returns (stored_filename, None) on success or (None, error_message).
    Checks: file chosen, .pdf extension, real PDF content, safe unique filename.
    The 5 MB size limit is enforced by Flask (MAX_CONTENT_LENGTH).
    """
    if file_storage is None or not file_storage.filename:
        return None, "Please choose a PDF file."
    if not allowed_file(file_storage.filename):
        return None, "Only PDF files are allowed."

    header = file_storage.stream.read(5)
    file_storage.stream.seek(0)
    if header != b"%PDF-":
        return None, "This file is not a valid PDF."

    cleaned = secure_filename(file_storage.filename) or "document.pdf"
    stored_name = f"{uuid.uuid4().hex[:12]}_{cleaned}"[:120]
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file_storage.save(upload_path(stored_name))
    return stored_name, None


def delete_upload(stored_name):
    """Remove an uploaded file from disk if it exists."""
    if not stored_name:
        return
    path = upload_path(stored_name)
    if os.path.isfile(path):
        os.remove(path)