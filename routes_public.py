"""
routes_public.py
The home page, the user dashboard, and template helpers that every page uses.
"""
from datetime import date

from flask import g, render_template, url_for

import db
import mock_engine as engine
from eligibility import (STATUS_ELIGIBLE, STATUS_VERIFY, check_job_eligibility, profile_from_user)
from utils import format_date, login_required


def register_routes(app):

    # If CSRF is switched off (only in automated tests), Flask-WTF does not define
    # csrf_token() for templates. This harmless fallback keeps templates working.
    if "csrf_token" not in app.jinja_env.globals:
        app.jinja_env.globals["csrf_token"] = lambda: ""

    @app.context_processor
    def inject_template_helpers():
        def safe_url(endpoint, fallback="#", **values):
            """url_for() if the page exists yet, otherwise the fallback path."""
            if endpoint in app.view_functions:
                return url_for(endpoint, **values)
            return fallback

        return {"safe_url": safe_url, "today_iso": date.today().isoformat()}

    # ------------------------------------------------------------------
    # Home page
    # ------------------------------------------------------------------
    @app.route("/", endpoint="index")
    def home():
        today = date.today().isoformat()

        latest_jobs = db.query_db(
            """SELECT * FROM jobs
               WHERE application_deadline IS NULL OR application_deadline >= ?
               ORDER BY application_start DESC, id DESC
               LIMIT 6""", (today,))

        popular_exams = db.query_db(
            """SELECT e.*, COUNT(je.job_id) AS job_count
               FROM exams e LEFT JOIN job_exams je ON je.exam_id = e.id
               GROUP BY e.id
               ORDER BY job_count DESC, e.name
               LIMIT 6""")

        resources = db.query_db("SELECT * FROM official_resources ORDER BY id LIMIT 5")

        mock_tests = db.query_db(
            """SELECT m.*, e.short_code, s.name AS subject_name
               FROM mock_tests m
               JOIN exams e    ON e.id = m.exam_id
               JOIN subjects s ON s.id = m.subject_id
               WHERE m.is_active = 1
               ORDER BY m.id LIMIT 4""")

        open_jobs = db.query_db(
            """SELECT COUNT(*) AS c FROM jobs
               WHERE application_deadline IS NULL OR application_deadline >= ?""",
            (today,), one=True)["c"]

        stats = {
            "jobs": db.count_rows("jobs"),
            "open_jobs": open_jobs,
            "exams": db.count_rows("exams"),
            "questions": db.count_rows("questions"),
            "mock_tests": db.count_rows("mock_tests"),
        }

        return render_template("index.html", stats=stats, latest_jobs=latest_jobs,
                               popular_exams=popular_exams, resources=resources,
                               mock_tests=mock_tests)

    # ------------------------------------------------------------------
    # User dashboard
    # ------------------------------------------------------------------
    @app.route("/dashboard", endpoint="dashboard")
    @login_required
    def dashboard_page():
        user = g.user
        user_id = user["id"]
        today = date.today()
        today_iso = today.isoformat()
        engine.finalize_expired_attempts(user_id)

        # ---- Jobs ----
        open_jobs = db.query_db(
            """SELECT * FROM jobs
               WHERE application_deadline IS NULL OR application_deadline >= ?
               ORDER BY application_deadline IS NULL, application_deadline, id""", (today_iso,))
        latest_jobs = db.query_db(
            """SELECT * FROM jobs
               WHERE application_deadline IS NULL OR application_deadline >= ?
               ORDER BY application_start DESC, id DESC LIMIT 4""", (today_iso,))

        age, level, state = profile_from_user(user)
        matches, verify_count = [], 0
        for job in open_jobs:
            status = check_job_eligibility(job, age, level, state, today)["status"]
            if status == STATUS_ELIGIBLE:
                matches.append(job)
            elif status == STATUS_VERIFY:
                verify_count += 1
        preferred = user["preferred_category"]
        if preferred:   # stable sort: preferred category first, deadline order kept
            matches.sort(key=lambda j: j["exam_category"] != preferred)
        match_total = len(matches)
        matches = matches[:6]

        saved_ids = {r["job_id"] for r in db.query_db(
            "SELECT job_id FROM saved_jobs WHERE user_id = ?", (user_id,))}
        saved_jobs = db.query_db(
            """SELECT j.* FROM jobs j JOIN saved_jobs s ON s.job_id = j.id
               WHERE s.user_id = ? ORDER BY s.saved_at DESC, s.id DESC LIMIT 4""", (user_id,))
        upcoming = [j for j in open_jobs if j["application_deadline"]][:5]

        # ---- Mock tests ----
        agg = db.query_db(
            """SELECT COUNT(*) AS n, AVG(score_percent) AS avg, MAX(score_percent) AS best
               FROM test_attempts WHERE user_id = ? AND status = 'submitted'""", (user_id,), one=True)
        summary = {"n": agg["n"], "best": agg["best"],
                   "avg": round(agg["avg"], 1) if agg["n"] else None}

        recent_attempts = db.query_db(
            """SELECT a.*, t.title AS test_title, e.short_code, s.name AS subject_name
               FROM test_attempts a
               JOIN mock_tests t ON t.id = a.mock_test_id
               JOIN exams e ON e.id = t.exam_id
               JOIN subjects s ON s.id = t.subject_id
               WHERE a.user_id = ? AND a.status = 'submitted'
               ORDER BY a.submitted_at DESC, a.id DESC LIMIT 5""", (user_id,))

        active_attempts = []
        for row in db.query_db(
                """SELECT a.id, a.started_at, t.title AS test_title, t.duration_minutes
                   FROM test_attempts a JOIN mock_tests t ON t.id = a.mock_test_id
                   WHERE a.user_id = ? AND a.status = 'in_progress' ORDER BY a.id DESC""", (user_id,)):
            left = engine.seconds_remaining(row, row["duration_minutes"])
            if left > 0:
                active_attempts.append({"id": row["id"], "title": row["test_title"],
                                        "minutes_left": max(1, int(left // 60))})

        chart = None
        score_rows = db.query_db(
            """SELECT score_percent, submitted_at FROM test_attempts
               WHERE user_id = ? AND status = 'submitted'
               ORDER BY submitted_at DESC, id DESC LIMIT 10""", (user_id,))
        if len(score_rows) >= 2:
            score_rows = list(reversed(score_rows))
            chart = {"labels": [format_date(r["submitted_at"][:10]) for r in score_rows],
                     "scores": [r["score_percent"] for r in score_rows]}

        # ---- Preparation progress ----
        tests_total = db.query_db("SELECT COUNT(*) AS c FROM mock_tests WHERE is_active = 1", one=True)["c"]
        test_progress = db.query_db(
            """SELECT t.id, t.title, MAX(a.score_percent) AS best, COUNT(a.id) AS attempts
               FROM mock_tests t JOIN test_attempts a ON a.mock_test_id = t.id
               WHERE a.user_id = ? AND a.status = 'submitted' AND t.is_active = 1
               GROUP BY t.id ORDER BY t.title""", (user_id,))
        tests_done = len(test_progress)
        progress_percent = int(tests_done / tests_total * 100) if tests_total else 0

        next_test = db.query_db(
            """SELECT t.*, e.short_code, s.name AS subject_name
               FROM mock_tests t
               JOIN exams e ON e.id = t.exam_id
               JOIN subjects s ON s.id = t.subject_id
               WHERE t.is_active = 1
                 AND t.id NOT IN (SELECT mock_test_id FROM test_attempts
                                  WHERE user_id = ? AND status = 'submitted')
               ORDER BY (e.category = ?) DESC, t.id LIMIT 1""", (user_id, preferred), one=True)

        return render_template(
            "dashboard.html", age=age, latest_jobs=latest_jobs, matches=matches,
            match_total=match_total, verify_count=verify_count, saved_jobs=saved_jobs,
            saved_ids=saved_ids, saved_total=len(saved_ids), upcoming=upcoming, summary=summary,
            recent_attempts=recent_attempts, active_attempts=active_attempts, chart=chart,
            tests_total=tests_total, tests_done=tests_done, progress_percent=progress_percent,
            test_progress=test_progress, next_test=next_test)