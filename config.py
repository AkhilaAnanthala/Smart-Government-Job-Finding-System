"""
config.py
Central place for all settings. Secrets come from the .env file,
never from the source code.
"""
import os
import secrets

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --------------------------------------------------------------------
# Lookup lists used by forms, validation and the eligibility checker.
# Key = level number stored in jobs.min_qualification_level
# --------------------------------------------------------------------
QUALIFICATION_LEVELS = {
    1: "10th Pass",
    2: "12th Pass / Intermediate",
    3: "ITI / Diploma",
    4: "Graduate (Bachelor's Degree)",
    5: "Post Graduate",
}

# Reverse lookup: label -> level number (e.g. "10th Pass" -> 1)
QUALIFICATION_LABEL_TO_LEVEL = {label: level for level, label in QUALIFICATION_LEVELS.items()}

EXAM_CATEGORIES = ["UPSC", "SSC", "Railway", "APPSC", "Other"]
GOVT_CATEGORIES = ["Central", "Andhra Pradesh"]
RESOURCE_TYPES = ["PDF", "Link", "Video", "Notes"]
RESOURCE_KINDS = ["Portal", "Mock Test", "Syllabus", "Previous Papers", "Notification"]
DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Puducherry", "Chandigarh", "Other",
]


class Config:
    # --- Security ---------------------------------------------------
    # If SECRET_KEY is missing from .env, a temporary random key is used.
    # (Sessions will reset every time the server restarts - fine for development.)
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours
    WTF_CSRF_TIME_LIMIT = None  # CSRF token valid for the whole session

    # --- Database ---------------------------------------------------
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "database", "portal.db")
    )

    # --- File uploads -----------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "materials")
    ALLOWED_EXTENSIONS = {"pdf"}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB limit for uploads

    # --- App behaviour ----------------------------------------------
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    JOBS_PER_PAGE = 9