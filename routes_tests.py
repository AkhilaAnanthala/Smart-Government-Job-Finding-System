"""
routes_tests.py
Mock tests: list, start, take (timer + autosave), submit, results and attempt history.
"""
import json
import math

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

import db
import mock_engine as engine
from utils import login_required

HISTORY_PER_PAGE = 10

TEST_SELECT = """SELECT t.*, e.name AS exam_name, e.short_code, s.name AS subject_name
                 FROM mock_tests t
                 JOIN exams e ON e.id = t.exam_id
                 JOIN subjects s ON s.id = t.subject_id"""


def _get_test(test_id):
    return db.query_db(TEST_SELECT + " WHERE t.id = ?", (test_id,), one=True)


def _own_attempt(attempt_id):
    """The attempt, only if it belongs to the logged-in user. Otherwise None."""
    return db.query_db("SELECT * FROM test_attempts WHERE id = ? AND user_id = ?",
                       (attempt_id, g.user["id"]), one=True)


def _own_attempt_or_404(attempt_id):
    attempt = _own_attempt(attempt_id)
    if attempt is None:
        abort(404)
    return attempt


def _id_arg(name):
    text = request.args.get(name, "").strip()
    if text.isascii() and text.isdigit() and len(text) <= 9:
        return int(text)
    return None


def register_routes(app):
    app.add_template_filter(engine.format_duration, "duration")

    # ------------------------------------------------------------------
    # Mock test list
    # ------------------------------------------------------------------
    @app.route("/mock-tests", endpoint="mock_tests")
    def mock_tests_page():
        exams_list = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
        exam_id = _id_arg("exam")
        if exam_id not in {e["id"] for e in exams_list}:
            exam_id = None

        clauses, params = ["t.is_active = 1"], []
        if exam_id:
            clauses.append("t.exam_id = ?")
            params.append(exam_id)

        tests = db.query_db(
            f"""SELECT t.*, e.name AS exam_name, e.short_code, s.name AS subject_name,
                       (SELECT COUNT(*) FROM questions q WHERE q.subject_id = t.subject_id) AS available
                FROM mock_tests t
                JOIN exams e ON e.id = t.exam_id
                JOIN subjects s ON s.id = t.subject_id
                WHERE {' AND '.join(clauses)}
                ORDER BY e.short_code, s.name""", params)

        stats, active = {}, {}
        if g.user:
            engine.finalize_expired_attempts(g.user["id"])
            for row in db.query_db(
                    """SELECT mock_test_id, COUNT(*) AS attempts, MAX(score_percent) AS best
                       FROM test_attempts WHERE user_id = ? AND status = 'submitted'
                       GROUP BY mock_test_id""", (g.user["id"],)):
                stats[row["mock_test_id"]] = row
            for row in db.query_db(
                    "SELECT id, mock_test_id FROM test_attempts WHERE user_id = ? AND status = 'in_progress'",
                    (g.user["id"],)):
                active[row["mock_test_id"]] = row["id"]

        external = db.query_db(
            "SELECT * FROM official_resources WHERE resource_kind = 'Mock Test' ORDER BY title")

        return render_template("mock_tests.html", tests=tests, exams_list=exams_list,
                               exam_id=exam_id, stats=stats, active=active, external=external)

    # ------------------------------------------------------------------
    # Start (or resume) a test
    # ------------------------------------------------------------------
    @app.route("/mock-tests/<int:test_id>/start", methods=["POST"], endpoint="start_test")
    def start_test_route(test_id):
        if g.user is None:
            flash("Please log in to take a mock test.", "warning")
            return redirect(url_for("login", next=url_for("mock_tests")))

        test = _get_test(test_id)
        if test is None or not test["is_active"]:
            abort(404)

        engine.finalize_expired_attempts(g.user["id"])
        existing = engine.get_active_attempt(g.user["id"], test_id)
        if existing:
            flash("You already have this test in progress. Resuming it.", "info")
            return redirect(url_for("take_test", attempt_id=existing["id"]))

        attempt_id = engine.start_attempt(g.user["id"], test)
        if attempt_id is None:
            flash("This test has no questions yet. Please try another test.", "warning")
            return redirect(url_for("mock_tests"))
        return redirect(url_for("take_test", attempt_id=attempt_id))

    # ------------------------------------------------------------------
    # The test page
    # ------------------------------------------------------------------
    @app.route("/attempts/<int:attempt_id>/take", endpoint="take_test")
    @login_required
    def take_test_page(attempt_id):
        attempt = _own_attempt_or_404(attempt_id)
        if attempt["status"] == "submitted":
            return redirect(url_for("results", attempt_id=attempt_id))

        test = _get_test(attempt["mock_test_id"])
        if test is None:
            abort(404)

        remaining = engine.seconds_remaining(attempt, test["duration_minutes"])
        rows = db.query_db(
            """SELECT ua.question_id, ua.question_order, ua.selected_option,
                      q.question_text, q.option_a, q.option_b, q.option_c, q.option_d
               FROM user_answers ua JOIN questions q ON q.id = ua.question_id
               WHERE ua.attempt_id = ? ORDER BY ua.question_order""", (attempt_id,))

        if remaining <= 0 or not rows:
            engine.finalize_attempt(attempt_id, test["duration_minutes"])
            flash("Time is up! Your test was submitted automatically." if rows
                  else "This test no longer has any questions.", "warning")
            return redirect(url_for("results", attempt_id=attempt_id))

        # NOTE: correct answers and explanations are NOT sent to the browser.
        payload = {
            "questions": [{
                "id": r["question_id"], "number": r["question_order"], "text": r["question_text"],
                "options": {"A": r["option_a"], "B": r["option_b"], "C": r["option_c"], "D": r["option_d"]},
            } for r in rows],
            "answers": {str(r["question_id"]): r["selected_option"]
                        for r in rows if r["selected_option"]},
            "remainingSeconds": int(remaining),
            "saveUrl": url_for("save_answer", attempt_id=attempt_id),
        }
        return render_template("take_test.html", attempt=attempt, test=test,
                               total=len(rows), payload=payload)

    # ------------------------------------------------------------------
    # Autosave one answer (called by mock_test.js with fetch)
    # ------------------------------------------------------------------
    @app.route("/attempts/<int:attempt_id>/answer", methods=["POST"], endpoint="save_answer")
    def save_answer_route(attempt_id):
        if g.user is None:
            return jsonify(ok=False, error="login_required"), 401
        attempt = _own_attempt(attempt_id)
        if attempt is None:
            return jsonify(ok=False, error="not_found"), 404
        if attempt["status"] != "in_progress":
            return jsonify(ok=False, error="already_submitted"), 409

        test = _get_test(attempt["mock_test_id"])
        remaining = engine.seconds_remaining(attempt, test["duration_minutes"])
        if remaining < -engine.SAVE_GRACE_SECONDS:
            return jsonify(ok=False, error="time_up"), 409

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(ok=False, error="bad_request"), 400
        question_id, option = data.get("question_id"), data.get("option")
        if not isinstance(question_id, int) or isinstance(question_id, bool) \
                or not 0 < question_id < 2 ** 31:
            return jsonify(ok=False, error="bad_question"), 400
        if option in (None, ""):
            option = None
        elif not isinstance(option, str) or option not in engine.VALID_OPTIONS:
            return jsonify(ok=False, error="bad_option"), 400

        if not engine.record_answer(attempt_id, question_id, option):
            return jsonify(ok=False, error="question_not_in_test"), 404
        return jsonify(ok=True, remaining=int(max(remaining, 0)))

    # ------------------------------------------------------------------
    # Final submit (form POST)
    # ------------------------------------------------------------------
    @app.route("/attempts/<int:attempt_id>/submit", methods=["POST"], endpoint="submit_test")
    def submit_test_route(attempt_id):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        attempt = _own_attempt_or_404(attempt_id)
        if attempt["status"] == "submitted":
            return redirect(url_for("results", attempt_id=attempt_id))

        test = _get_test(attempt["mock_test_id"])
        answers = None
        raw = request.form.get("answers", "")
        if raw and len(raw) <= 20000:
            try:
                parsed = json.loads(raw)
                answers = parsed if isinstance(parsed, dict) else None
            except ValueError:
                answers = None

        engine.finalize_attempt(attempt_id, test["duration_minutes"], submitted_answers=answers)
        flash("Test submitted. Your score has been saved.", "success")
        return redirect(url_for("results", attempt_id=attempt_id))

    # ------------------------------------------------------------------
    # Results with correct answers and explanations
    # ------------------------------------------------------------------
    @app.route("/attempts/<int:attempt_id>/results", endpoint="results")
    @login_required
    def results_page(attempt_id):
        attempt = _own_attempt_or_404(attempt_id)
        if attempt["status"] != "submitted":
            return redirect(url_for("take_test", attempt_id=attempt_id))

        test = _get_test(attempt["mock_test_id"])
        rows = db.query_db(
            """SELECT ua.question_order, ua.selected_option, ua.is_correct,
                      q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
                      q.correct_option, q.explanation, q.is_demo
               FROM user_answers ua JOIN questions q ON q.id = ua.question_id
               WHERE ua.attempt_id = ? ORDER BY ua.question_order""", (attempt_id,))

        total = len(rows)
        correct = attempt["correct_count"]
        unanswered = sum(1 for r in rows if r["selected_option"] is None)
        incorrect = total - correct - unanswered
        message, css_class = engine.score_feedback(attempt["score_percent"])

        return render_template("results.html", attempt=attempt, test=test, rows=rows, total=total,
                               correct=correct, incorrect=incorrect, unanswered=unanswered,
                               feedback=message, feedback_class=css_class)

    # ------------------------------------------------------------------
    # Attempt history
    # ------------------------------------------------------------------
    @app.route("/attempt-history", endpoint="attempt_history")
    @login_required
    def attempt_history_page():
        user_id = g.user["id"]
        engine.finalize_expired_attempts(user_id)

        exams_list = db.query_db("SELECT id, name, short_code FROM exams ORDER BY short_code")
        exam_id = _id_arg("exam")
        if exam_id not in {e["id"] for e in exams_list}:
            exam_id = None

        where, params = "a.user_id = ?", [user_id]
        if exam_id:
            where += " AND t.exam_id = ?"
            params.append(exam_id)

        base = """FROM test_attempts a
                  JOIN mock_tests t ON t.id = a.mock_test_id
                  JOIN exams e ON e.id = t.exam_id
                  JOIN subjects s ON s.id = t.subject_id"""
        total = db.query_db(f"SELECT COUNT(*) AS c {base} WHERE {where}", params, one=True)["c"]
        pages = max(1, math.ceil(total / HISTORY_PER_PAGE))
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        page = min(max(page, 1), pages)

        attempts = db.query_db(
            f"""SELECT a.*, t.title AS test_title, t.duration_minutes, e.short_code, s.name AS subject_name
                {base} WHERE {where}
                ORDER BY a.started_at DESC, a.id DESC LIMIT ? OFFSET ?""",
            params + [HISTORY_PER_PAGE, (page - 1) * HISTORY_PER_PAGE])

        agg = db.query_db(
            """SELECT COUNT(*) AS n, AVG(score_percent) AS avg, MAX(score_percent) AS best
               FROM test_attempts WHERE user_id = ? AND status = 'submitted'""", (user_id,), one=True)
        summary = {"n": agg["n"], "best": agg["best"],
                   "avg": round(agg["avg"], 1) if agg["n"] else None}

        return render_template("attempt_history.html", attempts=attempts, summary=summary, total=total,
                               page=page, pages=pages, exams_list=exams_list, exam_id=exam_id,
                               args={"exam": exam_id} if exam_id else {})