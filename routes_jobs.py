"""
routes_jobs.py
Job finder (search, filters, sorting, pagination), job details, bookmarks
and the eligibility checker page.
"""
import math
from datetime import date, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import db
from config import (EXAM_CATEGORIES, GOVT_CATEGORIES, INDIAN_STATES, QUALIFICATION_LEVELS)
from eligibility import check_job_eligibility, profile_from_user, summarize_results
from utils import is_safe_next_url, login_required

DEADLINE_FILTERS = {
    "": "Any deadline",
    "open": "Open now",
    "week": "Closing within 7 days",
    "month": "Closing within 30 days",
    "closed": "Already closed",
}
SORT_OPTIONS = {
    "deadline_asc": "Deadline: soonest first",
    "deadline_desc": "Deadline: latest first",
    "newest": "Recently opened",
}
SHOW_OPTIONS = {
    "all": "All results",
    "eligible": "Eligible only",
    "verify": "Needs verification only",
    "not_eligible": "Not eligible only",
}


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


def _saved_job_ids(user_id):
    rows = db.query_db("SELECT job_id FROM saved_jobs WHERE user_id = ?", (user_id,))
    return {row["job_id"] for row in rows}


def register_routes(app):

    # ------------------------------------------------------------------
    # Job finder
    # ------------------------------------------------------------------
    @app.route("/jobs", endpoint="jobs")
    def jobs_page():
        today = date.today()
        today_iso = today.isoformat()

        filters = {
            "q": " ".join(request.args.get("q", "").split())[:100],
            "govt": request.args.get("govt", "").strip(),
            "category": request.args.get("category", "").strip(),
            "qualification": request.args.get("qualification", "").strip(),
            "deadline": request.args.get("deadline", "").strip(),
            "sort": request.args.get("sort", "deadline_asc").strip(),
            "exam": request.args.get("exam", "").strip(),
        }
        # Throw away anything that is not an allowed value.
        if filters["govt"] not in GOVT_CATEGORIES:
            filters["govt"] = ""
        if filters["category"] not in EXAM_CATEGORIES:
            filters["category"] = ""
        if filters["qualification"] not in [str(level) for level in QUALIFICATION_LEVELS]:
            filters["qualification"] = ""
        if filters["deadline"] not in DEADLINE_FILTERS:
            filters["deadline"] = ""
        if filters["sort"] not in SORT_OPTIONS:
            filters["sort"] = "deadline_asc"

        exam_filter = None
        exam_text = filters["exam"]
        if exam_text.isascii() and exam_text.isdigit() and len(exam_text) <= 9:
            exam_filter = db.get_exam_by_id(int(exam_text))
        if exam_filter is None:
            filters["exam"] = ""

        # ---- Build the WHERE part (placeholders only, values go in params) ----
        clauses, params = [], []
        if filters["q"]:
            pattern = _like_pattern(filters["q"])
            clauses.append("(title LIKE ? ESCAPE '\\' OR organization LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        if filters["govt"]:
            clauses.append("govt_category = ?")
            params.append(filters["govt"])
        if filters["category"]:
            clauses.append("exam_category = ?")
            params.append(filters["category"])
        if filters["qualification"]:
            clauses.append("min_qualification_level <= ?")
            params.append(int(filters["qualification"]))
        if exam_filter is not None:
            clauses.append("id IN (SELECT job_id FROM job_exams WHERE exam_id = ?)")
            params.append(exam_filter["id"])

        if filters["deadline"] == "open":
            clauses.append("(application_deadline IS NULL OR application_deadline >= ?)")
            params.append(today_iso)
        elif filters["deadline"] in ("week", "month"):
            days = 7 if filters["deadline"] == "week" else 30
            clauses.append("application_deadline BETWEEN ? AND ?")
            params += [today_iso, (today + timedelta(days=days)).isoformat()]
        elif filters["deadline"] == "closed":
            clauses.append("application_deadline < ?")
            params.append(today_iso)

        where_sql = " AND ".join(clauses) if clauses else "1 = 1"

        # ---- Sorting (fixed SQL text chosen from a whitelist) ----
        if filters["sort"] == "deadline_desc":
            order_sql, order_params = "application_deadline IS NULL, application_deadline DESC, id", []
        elif filters["sort"] == "newest":
            order_sql, order_params = "application_start DESC, id DESC", []
        else:  # deadline_asc: open jobs soonest first, closed jobs at the end
            order_sql = ("CASE WHEN application_deadline IS NULL THEN 2 "
                         "WHEN application_deadline < ? THEN 1 ELSE 0 END, "
                         "application_deadline ASC, id")
            order_params = [today_iso]

        # ---- Pagination ----
        per_page = app.config["JOBS_PER_PAGE"]
        total = db.query_db(f"SELECT COUNT(*) AS c FROM jobs WHERE {where_sql}",
                            params, one=True)["c"]
        pages = max(1, math.ceil(total / per_page))
        page = min(_positive_int(request.args.get("page", 1)), pages)

        job_rows = db.query_db(
            f"SELECT * FROM jobs WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            params + order_params + [per_page, (page - 1) * per_page])

        # Filters to keep in the pagination links (page is added by the template).
        args = {k: v for k, v in filters.items()
                if v and not (k == "sort" and v == "deadline_asc")}

        saved_ids = _saved_job_ids(g.user["id"]) if g.user else set()

        return render_template(
            "jobs.html", jobs=job_rows, total=total, page=page, pages=pages,
            filters=filters, args=args, exam_filter=exam_filter, saved_ids=saved_ids,
            deadline_filters=DEADLINE_FILTERS, sort_options=SORT_OPTIONS)

    # ------------------------------------------------------------------
    # Job details
    # ------------------------------------------------------------------
    @app.route("/jobs/<int:job_id>", endpoint="job_details")
    def job_details_page(job_id):
        job = db.get_job_by_id(job_id)
        if job is None:
            abort(404)

        exams = db.get_exams_for_job(job_id)

        # Other jobs that use the same recruitment exam (the many-to-many link).
        related_jobs = db.query_db(
            """SELECT DISTINCT j.* FROM jobs j
               JOIN job_exams je ON je.job_id = j.id
               WHERE je.exam_id IN (SELECT exam_id FROM job_exams WHERE job_id = ?)
                 AND j.id != ?
               ORDER BY j.application_deadline LIMIT 4""", (job_id, job_id))

        is_saved = False
        eligibility_result = None
        if g.user:
            is_saved = job_id in _saved_job_ids(g.user["id"])
            age, level, state = profile_from_user(g.user)
            eligibility_result = check_job_eligibility(job, age, level, state)

        return render_template("job_details.html", job=job, exams=exams,
                               related_jobs=related_jobs, is_saved=is_saved,
                               result=eligibility_result)

    # ------------------------------------------------------------------
    # Save / unsave (bookmark toggle). POST only, protected by CSRF.
    # ------------------------------------------------------------------
    @app.route("/jobs/<int:job_id>/save", methods=["POST"], endpoint="save_job")
    def toggle_save_job(job_id):
        next_url = request.form.get("next", "")

        # Not using @login_required here: it would send the user back to this
        # POST-only URL after login, which would give a 405 error.
        if g.user is None:
            flash("Please log in to save jobs.", "warning")
            return redirect(url_for("login", next=next_url if is_safe_next_url(next_url) else ""))

        if db.get_job_by_id(job_id) is None:
            abort(404)

        existing = db.query_db("SELECT id FROM saved_jobs WHERE user_id = ? AND job_id = ?",
                               (g.user["id"], job_id), one=True)
        if existing:
            db.execute_db("DELETE FROM saved_jobs WHERE id = ?", (existing["id"],))
            flash("Job removed from your saved list.", "info")
        else:
            db.execute_db("INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?, ?)",
                          (g.user["id"], job_id))
            flash("Job saved. You can find it under Saved Jobs.", "success")

        if is_safe_next_url(next_url):
            return redirect(next_url)
        return redirect(url_for("job_details", job_id=job_id))

    # ------------------------------------------------------------------
    # Saved jobs page
    # ------------------------------------------------------------------
    @app.route("/saved-jobs", endpoint="saved_jobs")
    @login_required
    def saved_jobs_page():
        saved = db.query_db(
            """SELECT j.* FROM jobs j
               JOIN saved_jobs s ON s.job_id = j.id
               WHERE s.user_id = ?
               ORDER BY s.saved_at DESC, s.id DESC""", (g.user["id"],))
        return render_template("saved_jobs.html", jobs=saved,
                               saved_ids={row["id"] for row in saved})

    # ------------------------------------------------------------------
    # Smart eligibility checker
    # ------------------------------------------------------------------
    @app.route("/eligibility", endpoint="eligibility")
    def eligibility_page():
        args = request.args
        form = {
            "age": args.get("age", "").strip(),
            "qualification": args.get("qualification", "").strip(),
            "state": args.get("state", "").strip(),
            "govt": args.get("govt", "").strip(),
            "show": args.get("show", "all").strip(),
            "include_closed": args.get("include_closed") == "1",
        }
        if form["govt"] not in GOVT_CATEGORIES:
            form["govt"] = ""
        if form["show"] not in SHOW_OPTIONS:
            form["show"] = "all"

        errors = {}
        items, counts, ran = [], None, False
        age = level = state = None
        use_profile = args.get("use_profile") == "1"

        if use_profile:
            if g.user is None:
                flash("Please log in to use your saved profile.", "warning")
                return redirect(url_for("login", next=url_for("eligibility")))
            age, level, state = profile_from_user(g.user)
            form.update(age=str(age), qualification=str(level or ""), state=state)
            ran = True
            if level is None:
                errors["qualification"] = "Your profile qualification is not recognised. Update your profile."
        elif args.get("age") or args.get("qualification") or args.get("state"):
            ran = True
            if form["age"].isascii() and form["age"].isdigit() and 14 <= int(form["age"]) <= 70:
                age = int(form["age"])
            else:
                errors["age"] = "Age must be a whole number between 14 and 70."
            if form["qualification"].isdigit() and int(form["qualification"]) in QUALIFICATION_LEVELS:
                level = int(form["qualification"])
            else:
                errors["qualification"] = "Please select your highest qualification."
            if form["state"] in INDIAN_STATES:
                state = form["state"]
            else:
                errors["state"] = "Please select your state."
        elif g.user:
            # First visit by a logged-in user: pre-fill the form from the profile.
            p_age, p_level, p_state = profile_from_user(g.user)
            form.update(age=str(p_age), qualification=str(p_level or ""), state=p_state)

        if ran and not errors:
            clauses, params = [], []
            if form["govt"]:
                clauses.append("govt_category = ?")
                params.append(form["govt"])
            if not form["include_closed"]:
                clauses.append("(application_deadline IS NULL OR application_deadline >= ?)")
                params.append(date.today().isoformat())
            where_sql = " AND ".join(clauses) if clauses else "1 = 1"
            job_rows = db.query_db(
                f"SELECT * FROM jobs WHERE {where_sql} "
                f"ORDER BY application_deadline IS NULL, application_deadline, id", params)

            all_items = [{"job": job, "result": check_job_eligibility(job, age, level, state)}
                         for job in job_rows]
            counts = summarize_results(all_items)
            items = [i for i in all_items
                     if form["show"] == "all" or i["result"]["status"] == form["show"]]

        return render_template("eligibility.html", form=form, errors=errors, ran=ran,
                               items=items, counts=counts, show_options=SHOW_OPTIONS,
                               used_profile=use_profile)