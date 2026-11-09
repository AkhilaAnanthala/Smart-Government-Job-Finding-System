"""
routes_admin.py
Protected administrator area: users, jobs, exams, subjects, study materials,
previous papers, official links, mock tests, questions, results and statistics.

Every route uses @admin_required. All SQL uses ? placeholders; table and column
names inserted into SQL come only from the fixed lists in this file.
"""
import math
import sqlite3
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import db
from config import (DIFFICULTY_LEVELS, EXAM_CATEGORIES, GOVT_CATEGORIES, INDIAN_STATES,
                    RESOURCE_KINDS, RESOURCE_TYPES)
from utils import (admin_required, delete_upload, is_valid_http_url, parse_date,
                   save_pdf_upload)

PER_PAGE = 15
MAX_ID = 2 ** 31 - 1
OPTION_LETTERS = ("A", "B", "C", "D")
SHORT_CODE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
DEMO_VACANCY_NOTE = "Sample figure for demonstration, not official"

_TABLES = {"users", "jobs", "exams", "subjects", "study_materials", "previous_papers",
           "official_resources", "questions", "mock_tests"}

JOB_COLUMNS = ["title", "organization", "govt_category", "exam_category", "required_qualification",
               "min_qualification_level", "min_age", "max_age", "state_requirement", "vacancies",
               "vacancies_note", "application_start", "application_deadline", "salary",
               "description", "eligibility_text", "syllabus_pattern", "notification_url",
               "apply_url", "age_relaxation_verified", "is_demo"]
EXAM_COLUMNS = ["name", "short_code", "category", "conducting_body", "govt_level", "description",
                "exam_pattern", "syllabus_summary", "official_url"]
MATERIAL_COLUMNS = ["subject_id", "title", "description", "resource_type", "url", "is_official",
                    "file_path"]
PAPER_COLUMNS = ["exam_id", "title", "year", "url", "file_path", "is_official"]
RESOURCE_COLUMNS = ["title", "url", "description", "resource_kind", "exam_id", "last_verified"]
TEST_COLUMNS = ["title", "exam_id", "subject_id", "duration_minutes", "num_questions", "is_active"]
QUESTION_COLUMNS = ["subject_id", "question_text", "option_a", "option_b", "option_c", "option_d",
                    "correct_option", "explanation", "difficulty", "is_demo"]


# ====================================================================
# Generic helpers
# ====================================================================
def _like_pattern(text):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _page_info(total):
    """(page, pages, offset) from ?page= in the URL."""
    pages = max(1, math.ceil(total / PER_PAGE))
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    page = min(max(page, 1), pages)
    return page, pages, (page - 1) * PER_PAGE


def _to_id(text):
    text = (text or "").strip()
    if text.isascii() and text.isdigit() and len(text) <= 9:
        number = int(text)
        return number if 0 < number <= MAX_ID else None
    return None


def _arg_id(name):
    return _to_id(request.args.get(name, ""))


def _post_id(name):
    return _to_id(request.form.get(name, ""))


def _get(table, row_id):
    """One row by id from one of OUR tables, or None."""
    if table not in _TABLES or row_id is None:
        return None
    return db.query_db(f"SELECT * FROM {table} WHERE id = ?", (row_id,), one=True)


def _form_dict(row):
    """Row -> plain dict with None turned into '' (so templates never print 'None')."""
    return {key: ("" if value is None else value) for key, value in dict(row).items()}


def _checkbox(form, name):
    return 1 if form.get(name) == "1" else 0


def _url_args(filters):
    return {key: value for key, value in filters.items() if value not in (None, "")}


def _field(form, name, label, errors, limit=200, required=False, multiline=False):
    raw = form.get(name, "")
    value = raw.strip() if multiline else " ".join(raw.split())
    if required and not value:
        errors[name] = f"{label} is required."
    elif len(value) > limit:
        errors[name] = f"{label} must be at most {limit} characters."
    return value


def _int_field(form, name, label, errors, low, high, required=False):
    raw = form.get(name, "").strip()
    if not raw:
        if required:
            errors[name] = f"{label} is required."
        return None
    if not (raw.isascii() and raw.isdigit()) or len(raw) > 9:
        errors[name] = f"{label} must be a whole number."
        return None
    number = int(raw)
    if not low <= number <= high:
        errors[name] = f"{label} must be between {low} and {high}."
        return None
    return number


def _date_field(form, name, label, errors):
    raw = form.get(name, "").strip()
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        errors[name] = f"{label} must be a valid date."
        return None
    return parsed.isoformat()          # always stored as YYYY-MM-DD


def _url_field(form, name, label, errors):
    value = form.get(name, "").strip()
    if value and not is_valid_http_url(value):
        errors[name] = f"{label} must be a full http:// or https:// link."
    return value or None


def _choice(form, name, label, errors, allowed):
    value = form.get(name, "").strip()
    if value not in allowed:
        errors[name] = f"Please choose a valid {label}."
    return value


def _insert_row(table, columns, data, conn=None, commit=True):
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    return db.execute_db(sql, [data[c] for c in columns], conn=conn, commit=commit)


def _update_row(table, columns, data, row_id, conn=None, commit=True):
    sql = f"UPDATE {table} SET {', '.join(c + ' = ?' for c in columns)} WHERE id = ?"
    db.execute_db(sql, [data[c] for c in columns] + [row_id], conn=conn, commit=commit)


def _exam_choices():
    rows = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
    return [(r["id"], f"{r['short_code']} - {r['name']}") for r in rows]


def _subject_choices():
    rows = db.query_db(
        """SELECT s.id, s.name, e.short_code FROM subjects s
           JOIN exams e ON e.id = s.exam_id ORDER BY e.short_code, s.name""")
    return [(r["id"], f"{r['short_code']} - {r['name']}") for r in rows]


def _handle_file(form, files, existing_file, url, errors):
    """
    Decide what the file_path column should hold after an upload / replace / remove.
    Returns (file_path, new_upload, old_to_delete):
      file_path      value to store (None = no file)
      new_upload     name of a file saved just now (delete it if the database write fails)
      old_to_delete  previous file to delete after the database write succeeds
    """
    upload = files.get("file")
    has_upload = upload is not None and bool(upload.filename)
    remove = form.get("remove_file") == "1"

    if has_upload:
        stored, error = save_pdf_upload(upload)
        if error:
            errors["file"] = error
            return existing_file, None, None
        return stored, stored, existing_file
    if remove and existing_file:
        if not url:
            errors["file"] = "Cannot remove the file because no external link is set. Add a link first."
            return existing_file, None, None
        return None, None, existing_file
    if not existing_file and not url:
        errors["url"] = "Provide an external link or upload a PDF."
        return None, None, None
    return existing_file, None, None


def _upload_names_for_subject(subject_id):
    rows = db.query_db("SELECT file_path FROM study_materials WHERE subject_id = ? "
                       "AND file_path IS NOT NULL", (subject_id,))
    return [r["file_path"] for r in rows]


def _upload_names_for_exam(exam_id):
    rows = db.query_db(
        """SELECT m.file_path FROM study_materials m JOIN subjects s ON s.id = m.subject_id
           WHERE s.exam_id = ? AND m.file_path IS NOT NULL""", (exam_id,))
    names = [r["file_path"] for r in rows]
    rows = db.query_db("SELECT file_path FROM previous_papers WHERE exam_id = ? "
                       "AND file_path IS NOT NULL", (exam_id,))
    return names + [r["file_path"] for r in rows]


# ====================================================================
# Form parsers for the larger forms
# ====================================================================
def _parse_job_form(form):
    errors, data = {}, {}
    data["title"] = _field(form, "title", "Job title", errors, 200, True)
    data["organization"] = _field(form, "organization", "Organization", errors, 200, True)
    data["govt_category"] = _choice(form, "govt_category", "government category", errors, GOVT_CATEGORIES)
    data["exam_category"] = _choice(form, "exam_category", "exam category", errors, EXAM_CATEGORIES)
    data["required_qualification"] = _field(form, "required_qualification", "Required qualification",
                                            errors, 200, True)
    data["min_qualification_level"] = _int_field(form, "min_qualification_level",
                                                 "Minimum qualification level", errors, 1, 5, True)
    data["min_age"] = _int_field(form, "min_age", "Minimum age", errors, 14, 70)
    data["max_age"] = _int_field(form, "max_age", "Maximum age", errors, 14, 70)
    if data["min_age"] is not None and data["max_age"] is not None and data["min_age"] > data["max_age"]:
        errors["max_age"] = "Minimum age cannot be greater than maximum age."

    state = form.get("state_requirement", "").strip()
    if state and state not in INDIAN_STATES:
        errors["state_requirement"] = "Please choose a valid state."
    data["state_requirement"] = state or None

    data["vacancies"] = _int_field(form, "vacancies", "Vacancies", errors, 0, 10_000_000)
    data["vacancies_note"] = _field(form, "vacancies_note", "Vacancies note", errors, 200) or None
    data["application_start"] = _date_field(form, "application_start", "Application start", errors)
    data["application_deadline"] = _date_field(form, "application_deadline", "Application deadline", errors)
    if data["application_start"] and data["application_deadline"] \
            and data["application_deadline"] < data["application_start"]:
        errors["application_deadline"] = "Application deadline cannot be before the start date."

    data["salary"] = _field(form, "salary", "Salary", errors, 200) or None
    data["description"] = _field(form, "description", "Description", errors, 4000, multiline=True) or None
    data["eligibility_text"] = _field(form, "eligibility_text", "Eligibility text", errors, 4000,
                                      multiline=True) or None
    data["syllabus_pattern"] = _field(form, "syllabus_pattern", "Syllabus / pattern", errors, 4000,
                                      multiline=True) or None
    data["notification_url"] = _url_field(form, "notification_url", "Notification link", errors)
    data["apply_url"] = _url_field(form, "apply_url", "Application link", errors)
    data["age_relaxation_verified"] = _checkbox(form, "age_relaxation_verified")
    data["is_demo"] = _checkbox(form, "is_demo")
    if data["is_demo"] and data["vacancies"] is not None and not data["vacancies_note"]:
        data["vacancies_note"] = DEMO_VACANCY_NOTE      # keep demo figures clearly labelled

    valid_exam_ids = {r["id"] for r in db.query_db("SELECT id FROM exams")}
    exam_ids = []
    for text in form.getlist("exam_ids"):
        exam_id = _to_id(text)
        if exam_id in valid_exam_ids and exam_id not in exam_ids:
            exam_ids.append(exam_id)
    return data, exam_ids, errors


def _parse_exam_form(form, exam_id=None):
    errors = {}
    data = {
        "name": _field(form, "name", "Exam name", errors, 150, True),
        "short_code": _field(form, "short_code", "Short code", errors, 30, True).upper(),
        "category": _choice(form, "category", "category", errors, EXAM_CATEGORIES),
        "conducting_body": _field(form, "conducting_body", "Conducting body", errors, 200, True),
        "govt_level": _choice(form, "govt_level", "government level", errors, GOVT_CATEGORIES),
        "description": _field(form, "description", "Description", errors, 1000, multiline=True) or None,
        "exam_pattern": _field(form, "exam_pattern", "Exam pattern", errors, 3000, multiline=True) or None,
        "syllabus_summary": _field(form, "syllabus_summary", "Syllabus summary", errors, 3000,
                                   multiline=True) or None,
        "official_url": _url_field(form, "official_url", "Official website link", errors),
    }
    code = data["short_code"]
    if code and not set(code) <= SHORT_CODE_CHARS:
        errors["short_code"] = "Short code may contain only letters, numbers and hyphens."
    for column, label in (("name", "exam name"), ("short_code", "short code")):
        value = data[column]
        if value and column not in errors:
            clash = db.query_db(f"SELECT id FROM exams WHERE {column} = ? AND id != ?",
                                (value, exam_id or 0), one=True)
            if clash:
                errors[column] = f"This {label} is already used by another exam."
    return data, errors


def _parse_question_form(form):
    errors = {}
    subject_id = _int_field(form, "subject_id", "Subject", errors, 1, MAX_ID, True)
    if subject_id and _get("subjects", subject_id) is None:
        errors["subject_id"] = "Please choose a valid subject."
    data = {
        "subject_id": subject_id,
        "question_text": _field(form, "question_text", "Question", errors, 1000, True, multiline=True),
    }
    for letter in OPTION_LETTERS:
        key = f"option_{letter.lower()}"
        data[key] = _field(form, key, f"Option {letter}", errors, 300, True)
    options = [data[f"option_{letter.lower()}"].lower() for letter in OPTION_LETTERS]
    if all(options) and len(set(options)) < 4:
        errors["option_a"] = "The four options must all be different."
    data["correct_option"] = _choice(form, "correct_option", "correct answer", errors, OPTION_LETTERS)
    data["explanation"] = _field(form, "explanation", "Explanation", errors, 1000, multiline=True) or None
    data["difficulty"] = _choice(form, "difficulty", "difficulty", errors, DIFFICULTY_LEVELS)
    data["is_demo"] = _checkbox(form, "is_demo")
    return data, errors


# ====================================================================
# Routes
# ====================================================================
def register_routes(app):

    # ------------------------------------------------------------------
    # Overview and statistics
    # ------------------------------------------------------------------
    @app.route("/admin", endpoint="admin_dashboard")
    @admin_required
    def admin_dashboard_page():
        today = date.today().isoformat()

        def count(sql, args=()):
            return db.query_db(sql, args, one=True)["c"]

        agg = db.query_db(
            "SELECT COUNT(*) AS n, AVG(score_percent) AS avg FROM test_attempts WHERE status = 'submitted'",
            one=True)
        cards = [
            ("Registered users", count("SELECT COUNT(*) AS c FROM users"), "bi-people"),
            ("Administrators", count("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'"), "bi-shield-lock"),
            ("Job records", count("SELECT COUNT(*) AS c FROM jobs"), "bi-briefcase"),
            ("Open jobs", count("SELECT COUNT(*) AS c FROM jobs WHERE application_deadline IS NULL "
                                "OR application_deadline >= ?", (today,)), "bi-unlock"),
            ("Exams", count("SELECT COUNT(*) AS c FROM exams"), "bi-journal-text"),
            ("Subjects", count("SELECT COUNT(*) AS c FROM subjects"), "bi-diagram-3"),
            ("Study resources", count("SELECT COUNT(*) AS c FROM study_materials"), "bi-book"),
            ("Previous paper links", count("SELECT COUNT(*) AS c FROM previous_papers"), "bi-file-earmark-text"),
            ("Practice questions", count("SELECT COUNT(*) AS c FROM questions"), "bi-patch-question"),
            ("Mock tests", count("SELECT COUNT(*) AS c FROM mock_tests"), "bi-stopwatch"),
            ("Tests submitted", agg["n"], "bi-journal-check"),
            ("Average test score", f"{round(agg['avg'], 1):g}%" if agg["n"] else "-", "bi-graph-up"),
        ]

        alerts = []
        unverified = count("SELECT COUNT(*) AS c FROM official_resources WHERE last_verified IS NULL")
        if unverified:
            alerts.append({"text": f"{unverified} official resource link(s) have not been verified yet. "
                                   "Open each one and mark it verified.",
                           "endpoint": "admin_resources", "action": "Review links"})
        short = count("""SELECT COUNT(*) AS c FROM mock_tests t WHERE t.is_active = 1 AND
                         (SELECT COUNT(*) FROM questions q WHERE q.subject_id = t.subject_id) < t.num_questions""")
        if short:
            alerts.append({"text": f"{short} active mock test(s) have fewer questions than their question count setting.",
                           "endpoint": "admin_mock_tests", "action": "Review tests"})

        recent_users = db.query_db(
            "SELECT id, full_name, email, role, created_at FROM users ORDER BY id DESC LIMIT 5")
        recent_attempts = db.query_db(
            """SELECT a.id, a.score_percent, a.submitted_at, u.full_name, t.title AS test_title
               FROM test_attempts a JOIN users u ON u.id = a.user_id
               JOIN mock_tests t ON t.id = a.mock_test_id
               WHERE a.status = 'submitted' ORDER BY a.submitted_at DESC, a.id DESC LIMIT 6""")
        usage = db.query_db(
            """SELECT t.title, COUNT(a.id) AS attempts, AVG(a.score_percent) AS avg
               FROM mock_tests t LEFT JOIN test_attempts a
                    ON a.mock_test_id = t.id AND a.status = 'submitted'
               GROUP BY t.id ORDER BY attempts DESC, t.title LIMIT 8""")
        return render_template("admin/dashboard.html", cards=cards, alerts=alerts,
                               recent_users=recent_users, recent_attempts=recent_attempts, usage=usage)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    @app.route("/admin/users", endpoint="admin_users")
    @admin_required
    def admin_users_page():
        q = " ".join(request.args.get("q", "").split())[:100]
        role = request.args.get("role", "")
        if role not in ("user", "admin"):
            role = ""
        clauses, params = [], []
        if q:
            pattern = _like_pattern(q)
            clauses.append("(u.full_name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        if role:
            clauses.append("u.role = ?")
            params.append(role)
        where_sql = " AND ".join(clauses) or "1 = 1"

        total = db.query_db(f"SELECT COUNT(*) AS c FROM users u WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _page_info(total)
        users = db.query_db(
            f"""SELECT u.id, u.full_name, u.email, u.role, u.highest_qualification, u.state,
                       u.district, u.created_at,
                  (SELECT COUNT(*) FROM test_attempts a WHERE a.user_id = u.id AND a.status = 'submitted') AS attempts,
                  (SELECT COUNT(*) FROM saved_jobs s WHERE s.user_id = u.id) AS saved
                FROM users u WHERE {where_sql} ORDER BY u.id DESC LIMIT ? OFFSET ?""",
            params + [PER_PAGE, offset])
        filters = {"q": q, "role": role}
        return render_template("admin/users.html", users=users, total=total, page=page, pages=pages,
                               filters=filters, args=_url_args(filters))

    @app.route("/admin/users/<int:user_id>/role", methods=["POST"], endpoint="admin_user_role")
    @admin_required
    def admin_user_role(user_id):
        target = _get("users", user_id)
        if target is None:
            abort(404)
        role = request.form.get("role", "")
        if role not in ("user", "admin"):
            flash("Invalid role.", "danger")
        elif target["id"] == g.user["id"]:
            flash("You cannot change your own role.", "warning")
        else:
            db.execute_db("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            flash(f"{target['full_name']} is now {'an administrator' if role == 'admin' else 'a normal user'}.",
                  "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"], endpoint="admin_user_delete")
    @admin_required
    def admin_user_delete(user_id):
        target = _get("users", user_id)
        if target is None:
            abort(404)
        if target["id"] == g.user["id"]:
            flash("You cannot delete your own account.", "warning")
        else:
            db.execute_db("DELETE FROM users WHERE id = ?", (user_id,))
            flash(f"User {target['full_name']} and their attempts and saved jobs were deleted.", "info")
        return redirect(url_for("admin_users"))

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    def _job_context(form, errors, job_id, selected):
        return dict(form=form, errors=errors, job_id=job_id, selected_exam_ids=set(selected),
                    exams_all=db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code"))

    def _save_job(data, exam_ids, job_id=None):
        """Insert or update a job and its exam links in ONE transaction."""
        conn = db.get_db()
        try:
            if job_id is None:
                job_id = _insert_row("jobs", JOB_COLUMNS, data, conn=conn, commit=False)
            else:
                _update_row("jobs", JOB_COLUMNS, data, job_id, conn=conn, commit=False)
                db.execute_db("DELETE FROM job_exams WHERE job_id = ?", (job_id,), conn=conn, commit=False)
            for exam_id in exam_ids:
                db.execute_db("INSERT OR IGNORE INTO job_exams (job_id, exam_id) VALUES (?, ?)",
                              (job_id, exam_id), conn=conn, commit=False)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return job_id

    @app.route("/admin/jobs", endpoint="admin_jobs")
    @admin_required
    def admin_jobs_page():
        q = " ".join(request.args.get("q", "").split())[:100]
        govt = request.args.get("govt", "")
        category = request.args.get("category", "")
        if govt not in GOVT_CATEGORIES:
            govt = ""
        if category not in EXAM_CATEGORIES:
            category = ""
        clauses, params = [], []
        if q:
            pattern = _like_pattern(q)
            clauses.append("(title LIKE ? ESCAPE '\\' OR organization LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        if govt:
            clauses.append("govt_category = ?")
            params.append(govt)
        if category:
            clauses.append("exam_category = ?")
            params.append(category)
        where_sql = " AND ".join(clauses) or "1 = 1"

        total = db.query_db(f"SELECT COUNT(*) AS c FROM jobs WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _page_info(total)
        jobs = db.query_db(f"SELECT * FROM jobs WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
                           params + [PER_PAGE, offset])
        filters = {"q": q, "govt": govt, "category": category}
        return render_template("admin/jobs.html", jobs=jobs, total=total, page=page, pages=pages,
                               filters=filters, args=_url_args(filters))

    @app.route("/admin/jobs/new", methods=["GET", "POST"], endpoint="admin_job_new")
    @admin_required
    def admin_job_new():
        if request.method == "GET":
            form = {"govt_category": "Central", "exam_category": "SSC", "min_qualification_level": "4",
                    "is_demo": "1"}
            return render_template("admin/job_form.html", **_job_context(form, {}, None, []))

        data, exam_ids, errors = _parse_job_form(request.form)
        if not errors:
            try:
                _save_job(data, exam_ids)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values. Please check every field."
            else:
                flash("Job added.", "success")
                return redirect(url_for("admin_jobs"))
        flash("Please correct the highlighted fields.", "danger")
        return render_template("admin/job_form.html",
                               **_job_context(request.form.to_dict(), errors, None, exam_ids))

    @app.route("/admin/jobs/<int:job_id>/edit", methods=["GET", "POST"], endpoint="admin_job_edit")
    @admin_required
    def admin_job_edit(job_id):
        job = _get("jobs", job_id)
        if job is None:
            abort(404)
        if request.method == "GET":
            selected = [e["id"] for e in db.get_exams_for_job(job_id)]
            return render_template("admin/job_form.html", **_job_context(_form_dict(job), {}, job_id, selected))

        data, exam_ids, errors = _parse_job_form(request.form)
        if not errors:
            try:
                _save_job(data, exam_ids, job_id)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values. Please check every field."
            else:
                flash("Job updated.", "success")
                return redirect(url_for("admin_jobs"))
        flash("Please correct the highlighted fields.", "danger")
        return render_template("admin/job_form.html",
                               **_job_context(request.form.to_dict(), errors, job_id, exam_ids))

    @app.route("/admin/jobs/<int:job_id>/delete", methods=["POST"], endpoint="admin_job_delete")
    @admin_required
    def admin_job_delete(job_id):
        job = _get("jobs", job_id)
        if job is None:
            abort(404)
        db.execute_db("DELETE FROM jobs WHERE id = ?", (job_id,))
        flash(f"Job '{job['title']}' deleted.", "info")
        return redirect(url_for("admin_jobs"))

    # ------------------------------------------------------------------
    # Exams
    # ------------------------------------------------------------------
    @app.route("/admin/exams", endpoint="admin_exams")
    @admin_required
    def admin_exams_page():
        exams = db.query_db(
            """SELECT e.*,
                 (SELECT COUNT(*) FROM job_exams je WHERE je.exam_id = e.id) AS job_count,
                 (SELECT COUNT(*) FROM subjects s WHERE s.exam_id = e.id) AS subject_count,
                 (SELECT COUNT(*) FROM study_materials m JOIN subjects s2 ON s2.id = m.subject_id
                      WHERE s2.exam_id = e.id) AS material_count,
                 (SELECT COUNT(*) FROM questions q JOIN subjects s3 ON s3.id = q.subject_id
                      WHERE s3.exam_id = e.id) AS question_count
               FROM exams e ORDER BY e.category, e.name""")
        return render_template("admin/exams.html", exams=exams)

    def _exam_form(exam):
        exam_id = exam["id"] if exam else None
        if request.method == "GET":
            form = _form_dict(exam) if exam else {"category": "SSC", "govt_level": "Central"}
            return render_template("admin/exam_form.html", form=form, errors={}, exam_id=exam_id)
        data, errors = _parse_exam_form(request.form, exam_id)
        if not errors:
            try:
                if exam:
                    _update_row("exams", EXAM_COLUMNS, data, exam_id)
                else:
                    _insert_row("exams", EXAM_COLUMNS, data)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values. The name or code may already exist."
            else:
                flash("Exam saved.", "success")
                return redirect(url_for("admin_exams"))
        flash("Please correct the highlighted fields.", "danger")
        return render_template("admin/exam_form.html", form=request.form.to_dict(), errors=errors,
                               exam_id=exam_id)

    @app.route("/admin/exams/new", methods=["GET", "POST"], endpoint="admin_exam_new")
    @admin_required
    def admin_exam_new():
        return _exam_form(None)

    @app.route("/admin/exams/<int:exam_id>/edit", methods=["GET", "POST"], endpoint="admin_exam_edit")
    @admin_required
    def admin_exam_edit(exam_id):
        exam = _get("exams", exam_id)
        if exam is None:
            abort(404)
        return _exam_form(exam)

    @app.route("/admin/exams/<int:exam_id>/delete", methods=["POST"], endpoint="admin_exam_delete")
    @admin_required
    def admin_exam_delete(exam_id):
        exam = _get("exams", exam_id)
        if exam is None:
            abort(404)
        files = _upload_names_for_exam(exam_id)       # collected before the rows disappear
        db.execute_db("DELETE FROM exams WHERE id = ?", (exam_id,))
        for name in files:
            delete_upload(name)
        flash(f"Exam '{exam['name']}' and everything under it were deleted.", "info")
        return redirect(url_for("admin_exams"))

    # ------------------------------------------------------------------
    # Subjects (inline add / edit)
    # ------------------------------------------------------------------
    @app.route("/admin/subjects", endpoint="admin_subjects")
    @admin_required
    def admin_subjects_page():
        exam_id = _arg_id("exam")
        if exam_id and _get("exams", exam_id) is None:
            exam_id = None
        editing = None
        edit_id = _arg_id("edit")
        if edit_id:
            editing = db.query_db(
                "SELECT s.*, e.short_code FROM subjects s JOIN exams e ON e.id = s.exam_id WHERE s.id = ?",
                (edit_id,), one=True)
        where, params = ("s.exam_id = ?", [exam_id]) if exam_id else ("1 = 1", [])
        subjects = db.query_db(
            f"""SELECT s.*, e.short_code, e.name AS exam_name,
                  (SELECT COUNT(*) FROM study_materials m WHERE m.subject_id = s.id) AS material_count,
                  (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS question_count,
                  (SELECT COUNT(*) FROM mock_tests t WHERE t.subject_id = s.id) AS test_count
                FROM subjects s JOIN exams e ON e.id = s.exam_id
                WHERE {where} ORDER BY e.short_code, s.name""", params)
        form = _form_dict(editing) if editing else {"exam_id": exam_id or ""}
        return render_template("admin/subjects.html", subjects=subjects, exam_choices=_exam_choices(),
                               exam_id=exam_id, editing=editing, form=form)

    @app.route("/admin/subjects/save", methods=["POST"], endpoint="admin_subject_save")
    @admin_required
    def admin_subject_save():
        form = request.form
        subject_id = _post_id("id")
        existing = _get("subjects", subject_id) if subject_id else None
        if subject_id and existing is None:
            abort(404)
        errors = {}
        if existing:
            exam_id = existing["exam_id"]           # the exam of a subject cannot be changed
        else:
            exam_id = _int_field(form, "exam_id", "Exam", errors, 1, MAX_ID, True)
            if exam_id and _get("exams", exam_id) is None:
                errors["exam_id"] = "Please choose a valid exam."
        name = _field(form, "name", "Subject name", errors, 150, True)
        description = _field(form, "description", "Description", errors, 500, multiline=True)
        if not errors:
            clash = db.query_db("SELECT id FROM subjects WHERE exam_id = ? AND name = ? AND id != ?",
                                (exam_id, name, subject_id or 0), one=True)
            if clash:
                errors["name"] = "This exam already has a subject with that name."
        if not errors:
            data = {"exam_id": exam_id, "name": name, "description": description or None}
            try:
                if existing:
                    _update_row("subjects", ["name", "description"], data, subject_id)
                else:
                    _insert_row("subjects", ["exam_id", "name", "description"], data)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values."
        if errors:
            flash(" ".join(errors.values()), "danger")
            return redirect(url_for("admin_subjects", edit=subject_id, exam=exam_id))
        flash("Subject saved.", "success")
        return redirect(url_for("admin_subjects", exam=exam_id))

    @app.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"], endpoint="admin_subject_delete")
    @admin_required
    def admin_subject_delete(subject_id):
        subject = _get("subjects", subject_id)
        if subject is None:
            abort(404)
        files = _upload_names_for_subject(subject_id)
        db.execute_db("DELETE FROM subjects WHERE id = ?", (subject_id,))
        for name in files:
            delete_upload(name)
        flash(f"Subject '{subject['name']}' and its materials, questions and tests were deleted.", "info")
        return redirect(url_for("admin_subjects", exam=subject["exam_id"]))

    # ------------------------------------------------------------------
    # Study materials
    # ------------------------------------------------------------------
    @app.route("/admin/materials", endpoint="admin_materials")
    @admin_required
    def admin_materials_page():
        exam_id, subject_id = _arg_id("exam"), _arg_id("subject")
        q = " ".join(request.args.get("q", "").split())[:100]
        source = request.args.get("source", "")
        if source not in ("official", "additional"):
            source = ""
        clauses, params = [], []
        if q:
            pattern = _like_pattern(q)
            clauses.append("(m.title LIKE ? ESCAPE '\\' OR m.description LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        if exam_id:
            clauses.append("s.exam_id = ?")
            params.append(exam_id)
        if subject_id:
            clauses.append("m.subject_id = ?")
            params.append(subject_id)
        if source:
            clauses.append("m.is_official = ?")
            params.append(1 if source == "official" else 0)
        where_sql = " AND ".join(clauses) or "1 = 1"
        base = ("FROM study_materials m JOIN subjects s ON s.id = m.subject_id "
                "JOIN exams e ON e.id = s.exam_id")
        total = db.query_db(f"SELECT COUNT(*) AS c {base} WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _page_info(total)
        rows = db.query_db(
            f"""SELECT m.*, s.name AS subject_name, e.short_code {base} WHERE {where_sql}
                ORDER BY m.id DESC LIMIT ? OFFSET ?""", params + [PER_PAGE, offset])
        filters = {"q": q, "exam": exam_id, "subject": subject_id, "source": source}
        return render_template("admin/materials.html", materials=rows, total=total, page=page,
                               pages=pages, filters=filters, args=_url_args(filters),
                               exam_choices=_exam_choices(), subject_choices=_subject_choices())

    def _material_form(existing):
        context = dict(existing=existing, subject_choices=_subject_choices())
        if request.method == "GET":
            form = _form_dict(existing) if existing else {"resource_type": "Link"}
            return render_template("admin/material_form.html", form=form, errors={}, **context)

        form, errors = request.form, {}
        subject_id = _int_field(form, "subject_id", "Subject", errors, 1, MAX_ID, True)
        if subject_id and _get("subjects", subject_id) is None:
            errors["subject_id"] = "Please choose a valid subject."
        data = {
            "subject_id": subject_id,
            "title": _field(form, "title", "Title", errors, 200, True),
            "description": _field(form, "description", "Description", errors, 1000, multiline=True) or None,
            "resource_type": _choice(form, "resource_type", "resource type", errors, RESOURCE_TYPES),
            "url": _url_field(form, "url", "External link", errors),
            "is_official": _checkbox(form, "is_official"),
        }
        new_upload = old_file = None
        if not errors:
            data["file_path"], new_upload, old_file = _handle_file(
                form, request.files, existing["file_path"] if existing else None, data["url"], errors)
        if not errors:
            try:
                if existing:
                    _update_row("study_materials", MATERIAL_COLUMNS, data, existing["id"])
                else:
                    data["added_by"] = g.user["id"]
                    _insert_row("study_materials", MATERIAL_COLUMNS + ["added_by"], data)
            except sqlite3.IntegrityError:
                delete_upload(new_upload)
                errors["_form"] = "The database rejected these values."
            else:
                delete_upload(old_file)
                flash("Study material saved.", "success")
                return redirect(url_for("admin_materials"))
        flash("Please correct the highlighted fields.", "danger")
        return render_template("admin/material_form.html", form=form.to_dict(), errors=errors, **context)

    @app.route("/admin/materials/new", methods=["GET", "POST"], endpoint="admin_material_new")
    @admin_required
    def admin_material_new():
        return _material_form(None)

    @app.route("/admin/materials/<int:material_id>/edit", methods=["GET", "POST"],
               endpoint="admin_material_edit")
    @admin_required
    def admin_material_edit(material_id):
        existing = _get("study_materials", material_id)
        if existing is None:
            abort(404)
        return _material_form(existing)

    @app.route("/admin/materials/<int:material_id>/delete", methods=["POST"], endpoint="admin_material_delete")
    @admin_required
    def admin_material_delete(material_id):
        row = _get("study_materials", material_id)
        if row is None:
            abort(404)
        db.execute_db("DELETE FROM study_materials WHERE id = ?", (material_id,))
        delete_upload(row["file_path"])
        flash("Study material deleted.", "info")
        return redirect(url_for("admin_materials"))

    # ------------------------------------------------------------------
    # Previous papers (inline add / edit)
    # ------------------------------------------------------------------
    @app.route("/admin/papers", endpoint="admin_papers")
    @admin_required
    def admin_papers_page():
        exam_id = _arg_id("exam")
        editing = _get("previous_papers", _arg_id("edit"))
        where, params = ("p.exam_id = ?", [exam_id]) if exam_id else ("1 = 1", [])
        total = db.query_db(f"SELECT COUNT(*) AS c FROM previous_papers p WHERE {where}", params, one=True)["c"]
        page, pages, offset = _page_info(total)
        papers = db.query_db(
            f"""SELECT p.*, e.short_code FROM previous_papers p JOIN exams e ON e.id = p.exam_id
                WHERE {where} ORDER BY p.id DESC LIMIT ? OFFSET ?""", params + [PER_PAGE, offset])
        form = _form_dict(editing) if editing else {"exam_id": exam_id or ""}
        filters = {"exam": exam_id}
        return render_template("admin/papers.html", papers=papers, total=total, page=page, pages=pages,
                               filters=filters, args=_url_args(filters), exam_choices=_exam_choices(),
                               editing=editing, form=form)

    @app.route("/admin/papers/save", methods=["POST"], endpoint="admin_paper_save")
    @admin_required
    def admin_paper_save():
        form = request.form
        paper_id = _post_id("id")
        existing = _get("previous_papers", paper_id) if paper_id else None
        if paper_id and existing is None:
            abort(404)
        errors = {}
        exam_id = _int_field(form, "exam_id", "Exam", errors, 1, MAX_ID, True)
        if exam_id and _get("exams", exam_id) is None:
            errors["exam_id"] = "Please choose a valid exam."
        data = {
            "exam_id": exam_id,
            "title": _field(form, "title", "Title", errors, 200, True),
            "year": _int_field(form, "year", "Year", errors, 1990, 2100),
            "url": _url_field(form, "url", "External link", errors),
            "is_official": _checkbox(form, "is_official"),
        }
        new_upload = old_file = None
        if not errors:
            data["file_path"], new_upload, old_file = _handle_file(
                form, request.files, existing["file_path"] if existing else None, data["url"], errors)
        if not errors:
            try:
                if existing:
                    _update_row("previous_papers", PAPER_COLUMNS, data, paper_id)
                else:
                    _insert_row("previous_papers", PAPER_COLUMNS, data)
            except sqlite3.IntegrityError:
                delete_upload(new_upload)
                errors["_form"] = "The database rejected these values."
            else:
                delete_upload(old_file)
                flash("Previous paper saved.", "success")
                return redirect(url_for("admin_papers"))
        flash(" ".join(errors.values()), "danger")
        return redirect(url_for("admin_papers", edit=paper_id))

    @app.route("/admin/papers/<int:paper_id>/delete", methods=["POST"], endpoint="admin_paper_delete")
    @admin_required
    def admin_paper_delete(paper_id):
        row = _get("previous_papers", paper_id)
        if row is None:
            abort(404)
        db.execute_db("DELETE FROM previous_papers WHERE id = ?", (paper_id,))
        delete_upload(row["file_path"])
        flash("Previous paper deleted.", "info")
        return redirect(url_for("admin_papers"))

    # ------------------------------------------------------------------
    # Official resource links (inline add / edit)
    # ------------------------------------------------------------------
    @app.route("/admin/resources", endpoint="admin_resources")
    @admin_required
    def admin_resources_page():
        editing = _get("official_resources", _arg_id("edit"))
        resources = db.query_db(
            """SELECT r.*, e.short_code FROM official_resources r
               LEFT JOIN exams e ON e.id = r.exam_id ORDER BY r.resource_kind, r.title""")
        form = _form_dict(editing) if editing else {"resource_kind": "Portal"}
        return render_template("admin/official_resources.html", resources=resources,
                               exam_choices=_exam_choices(), editing=editing, form=form)

    @app.route("/admin/resources/save", methods=["POST"], endpoint="admin_resource_save")
    @admin_required
    def admin_resource_save():
        form = request.form
        resource_id = _post_id("id")
        existing = _get("official_resources", resource_id) if resource_id else None
        if resource_id and existing is None:
            abort(404)
        errors = {}
        data = {
            "title": _field(form, "title", "Title", errors, 150, True),
            "url": _url_field(form, "url", "Link", errors),
            "description": _field(form, "description", "Description", errors, 500, multiline=True) or None,
            "resource_kind": _choice(form, "resource_kind", "kind", errors, RESOURCE_KINDS),
            "last_verified": _date_field(form, "last_verified", "Last verified date", errors),
        }
        if not data["url"] and "url" not in errors:
            errors["url"] = "Link is required."
        exam_id = _int_field(form, "exam_id", "Exam", errors, 1, MAX_ID)
        if exam_id and _get("exams", exam_id) is None:
            errors["exam_id"] = "Please choose a valid exam."
        data["exam_id"] = exam_id
        if not errors:
            try:
                if existing:
                    if existing["url"] != data["url"] and not data["last_verified"]:
                        data["last_verified"] = None        # a changed link must be checked again
                    _update_row("official_resources", RESOURCE_COLUMNS, data, resource_id)
                else:
                    _insert_row("official_resources", RESOURCE_COLUMNS, data)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values."
        if errors:
            flash(" ".join(errors.values()), "danger")
            return redirect(url_for("admin_resources", edit=resource_id))
        flash("Official link saved.", "success")
        return redirect(url_for("admin_resources"))

    @app.route("/admin/resources/<int:resource_id>/verify", methods=["POST"], endpoint="admin_resource_verify")
    @admin_required
    def admin_resource_verify(resource_id):
        if _get("official_resources", resource_id) is None:
            abort(404)
        db.execute_db("UPDATE official_resources SET last_verified = ? WHERE id = ?",
                      (date.today().isoformat(), resource_id))
        flash("Link marked as verified today.", "success")
        return redirect(url_for("admin_resources"))

    @app.route("/admin/resources/<int:resource_id>/delete", methods=["POST"], endpoint="admin_resource_delete")
    @admin_required
    def admin_resource_delete(resource_id):
        if _get("official_resources", resource_id) is None:
            abort(404)
        db.execute_db("DELETE FROM official_resources WHERE id = ?", (resource_id,))
        flash("Official link deleted.", "info")
        return redirect(url_for("admin_resources"))

    # ------------------------------------------------------------------
    # Mock tests (inline add / edit)
    # ------------------------------------------------------------------
    @app.route("/admin/mock-tests", endpoint="admin_mock_tests")
    @admin_required
    def admin_mock_tests_page():
        editing = _get("mock_tests", _arg_id("edit"))
        tests = db.query_db(
            """SELECT t.*, e.short_code, s.name AS subject_name,
                 (SELECT COUNT(*) FROM questions q WHERE q.subject_id = t.subject_id) AS available,
                 (SELECT COUNT(*) FROM test_attempts a WHERE a.mock_test_id = t.id
                      AND a.status = 'submitted') AS attempts
               FROM mock_tests t JOIN exams e ON e.id = t.exam_id JOIN subjects s ON s.id = t.subject_id
               ORDER BY e.short_code, s.name""")
        form = _form_dict(editing) if editing else {"duration_minutes": 10, "num_questions": 10, "is_active": "1"}
        return render_template("admin/mock_tests.html", tests=tests, subject_choices=_subject_choices(),
                               editing=editing, form=form)

    @app.route("/admin/mock-tests/save", methods=["POST"], endpoint="admin_mock_test_save")
    @admin_required
    def admin_mock_test_save():
        form = request.form
        test_id = _post_id("id")
        existing = _get("mock_tests", test_id) if test_id else None
        if test_id and existing is None:
            abort(404)
        errors = {}
        subject = None
        subject_id = _int_field(form, "subject_id", "Subject", errors, 1, MAX_ID, True)
        if subject_id:
            subject = db.query_db(
                "SELECT s.*, e.short_code FROM subjects s JOIN exams e ON e.id = s.exam_id WHERE s.id = ?",
                (subject_id,), one=True)
            if subject is None:
                errors["subject_id"] = "Please choose a valid subject."
        duration = _int_field(form, "duration_minutes", "Duration (minutes)", errors, 1, 180, True)
        number = _int_field(form, "num_questions", "Number of questions", errors, 1, 100, True)
        title = _field(form, "title", "Title", errors, 150)
        if subject is not None:
            title = title or f"{subject['short_code']} - {subject['name']} Practice Test"
            clash = db.query_db("SELECT id FROM mock_tests WHERE exam_id = ? AND subject_id = ? AND id != ?",
                                (subject["exam_id"], subject["id"], test_id or 0), one=True)
            if clash:
                errors["subject_id"] = "This subject already has a mock test."
        if not errors:
            data = {"title": title, "exam_id": subject["exam_id"], "subject_id": subject["id"],
                    "duration_minutes": duration, "num_questions": number,
                    "is_active": _checkbox(form, "is_active")}
            try:
                if existing:
                    _update_row("mock_tests", TEST_COLUMNS, data, test_id)
                else:
                    _insert_row("mock_tests", TEST_COLUMNS, data)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values."
        if errors:
            flash(" ".join(errors.values()), "danger")
            return redirect(url_for("admin_mock_tests", edit=test_id))
        flash("Mock test saved.", "success")
        return redirect(url_for("admin_mock_tests"))

    @app.route("/admin/mock-tests/<int:test_id>/delete", methods=["POST"], endpoint="admin_mock_test_delete")
    @admin_required
    def admin_mock_test_delete(test_id):
        test = _get("mock_tests", test_id)
        if test is None:
            abort(404)
        db.execute_db("DELETE FROM mock_tests WHERE id = ?", (test_id,))
        flash(f"Mock test '{test['title']}' and its attempts were deleted.", "info")
        return redirect(url_for("admin_mock_tests"))

    # ------------------------------------------------------------------
    # Questions
    # ------------------------------------------------------------------
    @app.route("/admin/questions", endpoint="admin_questions")
    @admin_required
    def admin_questions_page():
        exam_id, subject_id = _arg_id("exam"), _arg_id("subject")
        q = " ".join(request.args.get("q", "").split())[:100]
        difficulty = request.args.get("difficulty", "")
        if difficulty not in DIFFICULTY_LEVELS:
            difficulty = ""
        clauses, params = [], []
        if q:
            clauses.append("q.question_text LIKE ? ESCAPE '\\'")
            params.append(_like_pattern(q))
        if exam_id:
            clauses.append("s.exam_id = ?")
            params.append(exam_id)
        if subject_id:
            clauses.append("q.subject_id = ?")
            params.append(subject_id)
        if difficulty:
            clauses.append("q.difficulty = ?")
            params.append(difficulty)
        where_sql = " AND ".join(clauses) or "1 = 1"
        base = "FROM questions q JOIN subjects s ON s.id = q.subject_id JOIN exams e ON e.id = s.exam_id"
        total = db.query_db(f"SELECT COUNT(*) AS c {base} WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _page_info(total)
        rows = db.query_db(
            f"""SELECT q.*, s.name AS subject_name, e.short_code {base} WHERE {where_sql}
                ORDER BY q.id DESC LIMIT ? OFFSET ?""", params + [PER_PAGE, offset])
        filters = {"q": q, "exam": exam_id, "subject": subject_id, "difficulty": difficulty}
        return render_template("admin/questions.html", questions=rows, total=total, page=page,
                               pages=pages, filters=filters, args=_url_args(filters),
                               exam_choices=_exam_choices(), subject_choices=_subject_choices())

    def _question_form(existing):
        context = dict(existing=existing, subject_choices=_subject_choices())
        if request.method == "GET":
            form = _form_dict(existing) if existing else {"difficulty": "Medium", "is_demo": "1"}
            return render_template("admin/question_form.html", form=form, errors={}, **context)
        data, errors = _parse_question_form(request.form)
        if not errors:
            try:
                if existing:
                    _update_row("questions", QUESTION_COLUMNS, data, existing["id"])
                else:
                    _insert_row("questions", QUESTION_COLUMNS, data)
            except sqlite3.IntegrityError:
                errors["_form"] = "The database rejected these values."
            else:
                flash("Question saved.", "success")
                return redirect(url_for("admin_questions", subject=data["subject_id"]))
        flash("Please correct the highlighted fields.", "danger")
        return render_template("admin/question_form.html", form=request.form.to_dict(), errors=errors, **context)

    @app.route("/admin/questions/new", methods=["GET", "POST"], endpoint="admin_question_new")
    @admin_required
    def admin_question_new():
        return _question_form(None)

    @app.route("/admin/questions/<int:question_id>/edit", methods=["GET", "POST"],
               endpoint="admin_question_edit")
    @admin_required
    def admin_question_edit(question_id):
        existing = _get("questions", question_id)
        if existing is None:
            abort(404)
        return _question_form(existing)

    @app.route("/admin/questions/<int:question_id>/delete", methods=["POST"], endpoint="admin_question_delete")
    @admin_required
    def admin_question_delete(question_id):
        row = _get("questions", question_id)
        if row is None:
            abort(404)
        db.execute_db("DELETE FROM questions WHERE id = ?", (question_id,))
        flash("Question deleted.", "info")
        return redirect(url_for("admin_questions", subject=row["subject_id"]))

    # ------------------------------------------------------------------
    # Mock test results (all users)
    # ------------------------------------------------------------------
    @app.route("/admin/results", endpoint="admin_results")
    @admin_required
    def admin_results_page():
        exam_id = _arg_id("exam")
        q = " ".join(request.args.get("q", "").split())[:100]
        clauses, params = ["a.status = 'submitted'"], []
        if exam_id:
            clauses.append("t.exam_id = ?")
            params.append(exam_id)
        if q:
            pattern = _like_pattern(q)
            clauses.append("(u.full_name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        where_sql = " AND ".join(clauses)
        base = ("FROM test_attempts a JOIN users u ON u.id = a.user_id "
                "JOIN mock_tests t ON t.id = a.mock_test_id JOIN exams e ON e.id = t.exam_id "
                "JOIN subjects s ON s.id = t.subject_id")
        agg = db.query_db(
            f"SELECT COUNT(*) AS n, AVG(a.score_percent) AS avg, MAX(a.score_percent) AS best "
            f"{base} WHERE {where_sql}", params, one=True)
        summary = {"n": agg["n"], "best": agg["best"], "avg": round(agg["avg"], 1) if agg["n"] else None}
        page, pages, offset = _page_info(agg["n"])
        rows = db.query_db(
            f"""SELECT a.*, u.full_name, u.email, t.title AS test_title, e.short_code, s.name AS subject_name
                {base} WHERE {where_sql} ORDER BY a.submitted_at DESC, a.id DESC LIMIT ? OFFSET ?""",
            params + [PER_PAGE, offset])
        filters = {"exam": exam_id, "q": q}
        return render_template("admin/results.html", attempts=rows, summary=summary, page=page, pages=pages,
                               filters=filters, args=_url_args(filters), exam_choices=_exam_choices())