"""
routes_prep.py
Preparation Hub: exams, syllabus, study materials, previous papers,
practice questions, and safe serving of uploaded PDFs.
"""
import math
import os
from urllib.parse import urlparse

from flask import abort, current_app, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

import db
from config import DIFFICULTY_LEVELS, EXAM_CATEGORIES, GOVT_CATEGORIES, RESOURCE_TYPES

MATERIALS_PER_PAGE = 12
QUESTIONS_PER_PAGE = 10
PAPERS_PER_PAGE = 15

SOURCE_OPTIONS = {
    "": "All sources",
    "official": "Official only",
    "additional": "Additional learning resources",
}


# --------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------
def _like_pattern(text):
    """Escape % and _ so they are searched literally, then wrap with % for LIKE."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _positive_int(value, default=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _id_arg(name):
    """Read a numeric id from the URL (?exam=3). Returns an int or None."""
    text = request.args.get(name, "").strip()
    if text.isascii() and text.isdigit() and len(text) <= 9:
        return int(text)
    return None


def _clean_text(name, limit=100):
    return " ".join(request.args.get(name, "").split())[:limit]


def _paginate(total, per_page):
    """Return (page, pages, offset) using ?page= from the URL."""
    pages = max(1, math.ceil(total / per_page))
    page = min(_positive_int(request.args.get("page", 1)), pages)
    return page, pages, (page - 1) * per_page


def _url_args(filters):
    """Keep only the filters that are set, so pagination links stay short."""
    return {key: value for key, value in filters.items() if value not in (None, "")}


def _host(url):
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def resources_for_exam(exam):
    """
    Official resources that belong to an exam: either linked directly through
    official_resources.exam_id, or hosted on the same website as the exam's official_url.
    """
    host = _host(exam["official_url"])
    rows = db.query_db("SELECT * FROM official_resources ORDER BY resource_kind, title")
    return [r for r in rows
            if r["exam_id"] == exam["id"] or (host and _host(r["url"]) == host)]


def _send_stored_pdf(stored_name, title):
    """
    Send an uploaded PDF. Only the file name saved in the database is used,
    and basename() removes any folder parts such as '../'.
    """
    folder = current_app.config["UPLOAD_FOLDER"]
    safe_name = os.path.basename(stored_name or "")
    if not safe_name or not os.path.isfile(os.path.join(folder, safe_name)):
        abort(404)
    download_name = (secure_filename(title) or "document") + ".pdf"
    return send_from_directory(
        folder, safe_name, mimetype="application/pdf",
        as_attachment=request.args.get("download") == "1",
        download_name=download_name)


def register_routes(app):

    # ------------------------------------------------------------------
    # Preparation hub (overview)
    # ------------------------------------------------------------------
    @app.route("/preparation", endpoint="preparation")
    def preparation_page():
        exams = db.query_db(
            """SELECT e.*,
                      (SELECT COUNT(*) FROM job_exams je WHERE je.exam_id = e.id) AS job_count
               FROM exams e ORDER BY e.name""")
        grouped = {}
        for exam in exams:
            grouped.setdefault(exam["category"], []).append(exam)

        resources = db.query_db("SELECT * FROM official_resources ORDER BY resource_kind, title")
        stats = {
            "exams": db.count_rows("exams"),
            "subjects": db.count_rows("subjects"),
            "materials": db.count_rows("study_materials"),
            "papers": db.count_rows("previous_papers"),
            "questions": db.count_rows("questions"),
        }
        return render_template("preparation.html", grouped=grouped, resources=resources, stats=stats)

    # ------------------------------------------------------------------
    # Examination list
    # ------------------------------------------------------------------
    @app.route("/exams", endpoint="exams")
    def exams_page():
        filters = {
            "q": _clean_text("q"),
            "category": request.args.get("category", "").strip(),
            "govt": request.args.get("govt", "").strip(),
        }
        if filters["category"] not in EXAM_CATEGORIES:
            filters["category"] = ""
        if filters["govt"] not in GOVT_CATEGORIES:
            filters["govt"] = ""

        clauses, params = [], []
        if filters["q"]:
            pattern = _like_pattern(filters["q"])
            clauses.append("(e.name LIKE ? ESCAPE '\\' OR e.short_code LIKE ? ESCAPE '\\' "
                           "OR e.conducting_body LIKE ? ESCAPE '\\')")
            params += [pattern, pattern, pattern]
        if filters["category"]:
            clauses.append("e.category = ?")
            params.append(filters["category"])
        if filters["govt"]:
            clauses.append("e.govt_level = ?")
            params.append(filters["govt"])
        where_sql = " AND ".join(clauses) if clauses else "1 = 1"

        exam_rows = db.query_db(
            f"""SELECT e.*,
                  (SELECT COUNT(*) FROM job_exams je WHERE je.exam_id = e.id) AS job_count,
                  (SELECT COUNT(*) FROM subjects s WHERE s.exam_id = e.id) AS subject_count,
                  (SELECT COUNT(*) FROM study_materials sm
                       JOIN subjects s2 ON s2.id = sm.subject_id
                       WHERE s2.exam_id = e.id) AS material_count,
                  (SELECT COUNT(*) FROM previous_papers p WHERE p.exam_id = e.id) AS paper_count,
                  (SELECT COUNT(*) FROM mock_tests t
                       WHERE t.exam_id = e.id AND t.is_active = 1) AS test_count
                FROM exams e WHERE {where_sql}
                ORDER BY e.category, e.name""", params)

        return render_template("exams.html", exams=exam_rows, filters=filters)

    # ------------------------------------------------------------------
    # Examination details
    # ------------------------------------------------------------------
    @app.route("/exams/<int:exam_id>", endpoint="exam_details")
    def exam_details_page(exam_id):
        exam = db.get_exam_by_id(exam_id)
        if exam is None:
            abort(404)

        subjects = db.query_db(
            """SELECT s.*,
                  (SELECT COUNT(*) FROM study_materials m WHERE m.subject_id = s.id) AS material_count,
                  (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS question_count
               FROM subjects s WHERE s.exam_id = ? ORDER BY s.name""", (exam_id,))

        papers = db.query_db(
            """SELECT p.*, e.name AS exam_name, e.short_code
               FROM previous_papers p JOIN exams e ON e.id = p.exam_id
               WHERE p.exam_id = ?
               ORDER BY p.year IS NULL, p.year DESC, p.title""", (exam_id,))

        tests = db.query_db(
            """SELECT t.*, s.name AS subject_name
               FROM mock_tests t JOIN subjects s ON s.id = t.subject_id
               WHERE t.exam_id = ? AND t.is_active = 1 ORDER BY s.name""", (exam_id,))

        return render_template(
            "exam_details.html", exam=exam, subjects=subjects, papers=papers, tests=tests,
            jobs=db.get_jobs_for_exam(exam_id), resources=resources_for_exam(exam))

    # ------------------------------------------------------------------
    # Syllabus and exam pattern for one exam
    # ------------------------------------------------------------------
    @app.route("/exams/<int:exam_id>/syllabus", endpoint="syllabus")
    def syllabus_page(exam_id):
        exam = db.get_exam_by_id(exam_id)
        if exam is None:
            abort(404)

        subjects = db.query_db(
            """SELECT s.*,
                  (SELECT COUNT(*) FROM study_materials m WHERE m.subject_id = s.id) AS material_count,
                  (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS question_count
               FROM subjects s WHERE s.exam_id = ? ORDER BY s.name""", (exam_id,))
        syllabus_links = [r for r in resources_for_exam(exam) if r["resource_kind"] == "Syllabus"]
        return render_template("syllabus.html", exam=exam, subjects=subjects,
                               syllabus_links=syllabus_links)

    # ------------------------------------------------------------------
    # Study materials
    # ------------------------------------------------------------------
    @app.route("/materials", endpoint="materials")
    def materials_page():
        exams_list = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
        subjects_list = db.query_db(
            """SELECT s.id, s.name, s.exam_id FROM subjects s
               JOIN exams e ON e.id = s.exam_id ORDER BY e.short_code, s.name""")

        exam_id = _id_arg("exam")
        subject_id = _id_arg("subject")
        if exam_id not in {e["id"] for e in exams_list}:
            exam_id = None
        if subject_id not in {s["id"] for s in subjects_list}:
            subject_id = None

        filters = {
            "q": _clean_text("q"),
            "exam": exam_id,
            "subject": subject_id,
            "type": request.args.get("type", "").strip(),
            "source": request.args.get("source", "").strip(),
        }
        if filters["type"] not in RESOURCE_TYPES:
            filters["type"] = ""
        if filters["source"] not in ("official", "additional"):
            filters["source"] = ""

        clauses, params = [], []
        if filters["q"]:
            pattern = _like_pattern(filters["q"])
            clauses.append("(m.title LIKE ? ESCAPE '\\' OR m.description LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        if exam_id:
            clauses.append("s.exam_id = ?")
            params.append(exam_id)
        if subject_id:
            clauses.append("m.subject_id = ?")
            params.append(subject_id)
        if filters["type"]:
            clauses.append("m.resource_type = ?")
            params.append(filters["type"])
        if filters["source"]:
            clauses.append("m.is_official = ?")
            params.append(1 if filters["source"] == "official" else 0)
        where_sql = " AND ".join(clauses) if clauses else "1 = 1"

        base = """FROM study_materials m
                  JOIN subjects s ON s.id = m.subject_id
                  JOIN exams e ON e.id = s.exam_id"""
        total = db.query_db(f"SELECT COUNT(*) AS c {base} WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _paginate(total, MATERIALS_PER_PAGE)

        rows = db.query_db(
            f"""SELECT m.*, s.name AS subject_name, s.exam_id, e.name AS exam_name, e.short_code
                {base} WHERE {where_sql}
                ORDER BY m.is_official DESC, e.short_code, s.name, m.title
                LIMIT ? OFFSET ?""", params + [MATERIALS_PER_PAGE, offset])

        return render_template(
            "materials.html", materials=rows, total=total, page=page, pages=pages,
            filters=filters, args=_url_args(filters), exams_list=exams_list,
            subjects_list=subjects_list, source_options=SOURCE_OPTIONS)

    @app.route("/materials/<int:material_id>/file", endpoint="material_file")
    def material_file(material_id):
        row = db.query_db("SELECT title, file_path FROM study_materials WHERE id = ?",
                          (material_id,), one=True)
        if row is None or not row["file_path"]:
            abort(404)
        return _send_stored_pdf(row["file_path"], row["title"])

    # ------------------------------------------------------------------
    # Previous question papers
    # ------------------------------------------------------------------
    @app.route("/previous-papers", endpoint="previous_papers")
    def previous_papers_page():
        exams_list = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
        exam_id = _id_arg("exam")
        if exam_id not in {e["id"] for e in exams_list}:
            exam_id = None

        filters = {
            "exam": exam_id,
            "year": _id_arg("year"),
            "source": request.args.get("source", "").strip(),
        }
        if filters["source"] not in ("official", "additional"):
            filters["source"] = ""

        clauses, params = [], []
        if exam_id:
            clauses.append("p.exam_id = ?")
            params.append(exam_id)
        if filters["year"]:
            clauses.append("p.year = ?")
            params.append(filters["year"])
        if filters["source"]:
            clauses.append("p.is_official = ?")
            params.append(1 if filters["source"] == "official" else 0)
        where_sql = " AND ".join(clauses) if clauses else "1 = 1"

        total = db.query_db(f"SELECT COUNT(*) AS c FROM previous_papers p WHERE {where_sql}",
                            params, one=True)["c"]
        page, pages, offset = _paginate(total, PAPERS_PER_PAGE)

        rows = db.query_db(
            f"""SELECT p.*, e.name AS exam_name, e.short_code
                FROM previous_papers p JOIN exams e ON e.id = p.exam_id
                WHERE {where_sql}
                ORDER BY p.is_official DESC, e.short_code, p.year IS NULL, p.year DESC, p.title
                LIMIT ? OFFSET ?""", params + [PAPERS_PER_PAGE, offset])

        years = [r["year"] for r in db.query_db(
            "SELECT DISTINCT year FROM previous_papers WHERE year IS NOT NULL ORDER BY year DESC")]
        official_links = []
        if not exam_id and not filters["year"] and not filters["source"]:
            official_links = db.query_db(
                "SELECT * FROM official_resources WHERE resource_kind = 'Previous Papers' ORDER BY title")

        return render_template(
            "previous_papers.html", papers=rows, total=total, page=page, pages=pages,
            filters=filters, args=_url_args(filters), exams_list=exams_list, years=years,
            source_options=SOURCE_OPTIONS, official_links=official_links)

    @app.route("/previous-papers/<int:paper_id>/file", endpoint="paper_file")
    def paper_file(paper_id):
        row = db.query_db("SELECT title, file_path FROM previous_papers WHERE id = ?",
                          (paper_id,), one=True)
        if row is None or not row["file_path"]:
            abort(404)
        return _send_stored_pdf(row["file_path"], row["title"])

    # ------------------------------------------------------------------
    # Practice questions (study view with answers hidden until clicked)
    # ------------------------------------------------------------------
    @app.route("/practice-questions", endpoint="practice_questions")
    def practice_questions_page():
        exams_list = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
        subjects_list = db.query_db(
            """SELECT s.id, s.name, s.exam_id FROM subjects s
               JOIN exams e ON e.id = s.exam_id ORDER BY e.short_code, s.name""")

        exam_id = _id_arg("exam")
        subject_id = _id_arg("subject")
        if exam_id not in {e["id"] for e in exams_list}:
            exam_id = None
        if subject_id not in {s["id"] for s in subjects_list}:
            subject_id = None

        filters = {
            "exam": exam_id,
            "subject": subject_id,
            "difficulty": request.args.get("difficulty", "").strip(),
        }
        if filters["difficulty"] not in DIFFICULTY_LEVELS:
            filters["difficulty"] = ""

        clauses, params = [], []
        if exam_id:
            clauses.append("s.exam_id = ?")
            params.append(exam_id)
        if subject_id:
            clauses.append("q.subject_id = ?")
            params.append(subject_id)
        if filters["difficulty"]:
            clauses.append("q.difficulty = ?")
            params.append(filters["difficulty"])
        where_sql = " AND ".join(clauses) if clauses else "1 = 1"

        base = """FROM questions q
                  JOIN subjects s ON s.id = q.subject_id
                  JOIN exams e ON e.id = s.exam_id"""
        total = db.query_db(f"SELECT COUNT(*) AS c {base} WHERE {where_sql}", params, one=True)["c"]
        page, pages, offset = _paginate(total, QUESTIONS_PER_PAGE)

        rows = db.query_db(
            f"""SELECT q.*, s.name AS subject_name, e.short_code
                {base} WHERE {where_sql}
                ORDER BY e.short_code, s.name, q.id
                LIMIT ? OFFSET ?""", params + [QUESTIONS_PER_PAGE, offset])

        return render_template(
            "practice_questions.html", questions=rows, total=total, page=page, pages=pages,
            offset=offset, filters=filters, args=_url_args(filters), exams_list=exams_list,
            subjects_list=subjects_list)