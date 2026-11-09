"""
db.py
Database helper functions for the whole project.

Rules used everywhere:
  * Every query uses ? placeholders (parameterized SQL) -> prevents SQL injection.
  * Foreign keys are switched ON for every connection (SQLite needs this each time).
  * Rows come back as sqlite3.Row, so you can write row["title"] instead of row[0].
"""
import os
import sqlite3
from contextlib import contextmanager

from flask import g, current_app

from config import BASE_DIR, Config

SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# Tables in the order they must be created (parents first).
# Used when resetting the database (dropped in reverse order).
ALL_TABLES = [
    "users", "exams", "jobs", "job_exams", "subjects", "study_materials",
    "previous_papers", "official_resources", "questions", "mock_tests",
    "test_attempts", "user_answers", "saved_jobs",
]


# --------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------
def get_connection(path=None):
    """Open a new SQLite connection (works with or without Flask)."""
    path = path or Config.DATABASE_PATH
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return the connection for the current web request (created once per request)."""
    if "db" not in g:
        g.db = get_connection(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(error=None):
    """Called automatically by Flask at the end of every request."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    """Register the cleanup function with the Flask app (call once in app.py)."""
    app.teardown_appcontext(close_db)


@contextmanager
def standalone_db(path=None):
    """
    Use in scripts that run outside Flask:
        with standalone_db() as conn:
            query_db("SELECT 1", conn=conn)
    """
    conn = get_connection(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------
def query_db(sql, args=(), one=False, conn=None):
    """
    Run a SELECT.
      one=False -> list of rows
      one=True  -> a single row, or None if nothing found
    """
    conn = conn or get_db()
    cur = conn.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute_db(sql, args=(), conn=None, commit=True):
    """
    Run INSERT / UPDATE / DELETE. Returns the id of the inserted row
    (useful after INSERT). Set commit=False to batch many writes.
    """
    conn = conn or get_db()
    cur = conn.execute(sql, args)
    last_id = cur.lastrowid
    cur.close()
    if commit:
        conn.commit()
    return last_id


# --------------------------------------------------------------------
# Database creation
# --------------------------------------------------------------------
def init_db(conn=None, reset=False):
    """
    Create all tables from schema.sql.
    reset=True deletes every table first (all data is lost!).
    """
    own_connection = conn is None
    conn = conn or get_connection()
    try:
        if reset:
            conn.execute("PRAGMA foreign_keys = OFF")
            for table in reversed(ALL_TABLES):
                conn.execute(f"DROP TABLE IF EXISTS {table}")  # names come from our fixed list
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        if own_connection:
            conn.close()


# --------------------------------------------------------------------
# Small reusable lookups (used by many routes)
# --------------------------------------------------------------------
def get_user_by_id(user_id, conn=None):
    return query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True, conn=conn)


def get_user_by_email(email, conn=None):
    return query_db(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),), one=True, conn=conn
    )


def create_user(full_name, email, password_hash, date_of_birth, highest_qualification,
                state, district, preferred_category=None, role="user", conn=None):
    """Insert a new user. The password must ALREADY be hashed. Returns the new user id."""
    return execute_db(
        """INSERT INTO users
           (full_name, email, password_hash, date_of_birth, highest_qualification,
            state, district, preferred_category, role)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (full_name.strip(), email.strip().lower(), password_hash, date_of_birth,
         highest_qualification, state, district, preferred_category, role),
        conn=conn,
    )


def get_job_by_id(job_id, conn=None):
    return query_db("SELECT * FROM jobs WHERE id = ?", (job_id,), one=True, conn=conn)


def get_exam_by_id(exam_id, conn=None):
    return query_db("SELECT * FROM exams WHERE id = ?", (exam_id,), one=True, conn=conn)


def get_exams_for_job(job_id, conn=None):
    """All recruitment exams linked to a job (through the job_exams mapping table)."""
    return query_db(
        """SELECT e.* FROM exams e
           JOIN job_exams je ON je.exam_id = e.id
           WHERE je.job_id = ? ORDER BY e.name""",
        (job_id,), conn=conn,
    )


def get_jobs_for_exam(exam_id, conn=None):
    """All jobs that use a given exam (many jobs can share one exam)."""
    return query_db(
        """SELECT j.* FROM jobs j
           JOIN job_exams je ON je.job_id = j.id
           WHERE je.exam_id = ? ORDER BY j.application_deadline""",
        (exam_id,), conn=conn,
    )


def count_rows(table, conn=None):
    """Count rows in one of OUR tables (name is checked against a fixed list)."""
    if table not in ALL_TABLES:
        raise ValueError("Unknown table name")
    row = query_db(f"SELECT COUNT(*) AS c FROM {table}", one=True, conn=conn)
    return row["c"]