"""
mock_engine.py
Server-side logic for mock tests: choosing questions, timing, saving answers, scoring.

The browser only displays questions and sends selections. The time limit and the
score are decided here, so they cannot be changed from the browser.
Times are stored in UTC as 'YYYY-MM-DD HH:MM:SS'.
"""
import random
from datetime import datetime, timezone

import db

DB_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SAVE_GRACE_SECONDS = 5       # an autosave may arrive a little after time is up
SUBMIT_GRACE_SECONDS = 30    # the automatic submit at 0:00 may arrive a little late
VALID_OPTIONS = ("A", "B", "C", "D")
MAX_SUBMITTED_ANSWERS = 200


# --------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_db_time(moment):
    return moment.strftime(DB_TIME_FORMAT)


def from_db_time(text):
    return datetime.strptime(text, DB_TIME_FORMAT)


def seconds_remaining(attempt, duration_minutes, now=None):
    """Seconds left for an attempt (negative once the time is over)."""
    now = now or utc_now()
    elapsed = (now - from_db_time(attempt["started_at"])).total_seconds()
    return duration_minutes * 60 - elapsed


def format_duration(seconds):
    """123 -> '2 min 03 sec'. Used as the template filter 'duration'."""
    if seconds is None:
        return "-"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes} min {secs:02d} sec"


def score_feedback(percent):
    """(message, bootstrap colour) for a score."""
    if percent >= 80:
        return "Excellent work!", "success"
    if percent >= 60:
        return "Good effort. Keep practising!", "primary"
    if percent >= 40:
        return "Fair start. Review the explanations below.", "warning"
    return "Needs more practice. Study the topic and try again.", "danger"


# --------------------------------------------------------------------
# Starting an attempt
# --------------------------------------------------------------------
def get_active_attempt(user_id, test_id):
    return db.query_db(
        """SELECT * FROM test_attempts
           WHERE user_id = ? AND mock_test_id = ? AND status = 'in_progress'
           ORDER BY id DESC LIMIT 1""", (user_id, test_id), one=True)


def start_attempt(user_id, test):
    """
    Create an attempt with a random, fixed set of questions.
    `test` is a mock_tests row. Returns the attempt id, or None if the subject has no questions.
    """
    rows = db.query_db("SELECT id FROM questions WHERE subject_id = ?", (test["subject_id"],))
    question_ids = [row["id"] for row in rows]
    if not question_ids:
        return None
    random.shuffle(question_ids)
    question_ids = question_ids[: test["num_questions"]]

    conn = db.get_db()
    try:
        attempt_id = db.execute_db(
            """INSERT INTO test_attempts (user_id, mock_test_id, started_at, total_questions)
               VALUES (?, ?, ?, ?)""",
            (user_id, test["id"], to_db_time(utc_now()), len(question_ids)),
            conn=conn, commit=False)
        for order, question_id in enumerate(question_ids, start=1):
            db.execute_db(
                "INSERT INTO user_answers (attempt_id, question_id, question_order) VALUES (?, ?, ?)",
                (attempt_id, question_id, order), conn=conn, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return attempt_id


# --------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------
def record_answer(attempt_id, question_id, option):
    """Save one selection (option is 'A'-'D' or None to clear). False if the question isn't in this attempt."""
    row = db.query_db("SELECT id FROM user_answers WHERE attempt_id = ? AND question_id = ?",
                      (attempt_id, question_id), one=True)
    if row is None:
        return False
    db.execute_db("UPDATE user_answers SET selected_option = ? WHERE id = ?", (option, row["id"]))
    return True


# --------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------
def finalize_attempt(attempt_id, duration_minutes, submitted_answers=None, now=None):
    """
    Close an attempt and calculate the score on the server.
    submitted_answers: optional {question_id: 'A'-'D' or None} sent with the submit form.
    It is used only if the submit arrives before the deadline plus the grace period.
    Returns True if this call closed the attempt, False if it was already closed.
    """
    conn = db.get_db()
    attempt = db.query_db("SELECT * FROM test_attempts WHERE id = ?", (attempt_id,), one=True, conn=conn)
    if attempt is None or attempt["status"] != "in_progress":
        return False

    now = now or utc_now()
    elapsed = (now - from_db_time(attempt["started_at"])).total_seconds()
    limit_seconds = duration_minutes * 60

    if submitted_answers and elapsed <= limit_seconds + SUBMIT_GRACE_SECONDS:
        for key, value in list(submitted_answers.items())[:MAX_SUBMITTED_ANSWERS]:
            try:
                question_id = int(key)
            except (TypeError, ValueError):
                continue
            if not 0 < question_id < 2 ** 31:
                continue
            if value is None or value == "":
                letter = None
            elif isinstance(value, str) and value in VALID_OPTIONS:
                letter = value
            else:
                continue
            conn.execute(
                "UPDATE user_answers SET selected_option = ? WHERE attempt_id = ? AND question_id = ?",
                (letter, attempt_id, question_id))

    rows = db.query_db(
        """SELECT ua.id, ua.selected_option, q.correct_option
           FROM user_answers ua JOIN questions q ON q.id = ua.question_id
           WHERE ua.attempt_id = ?""", (attempt_id,), conn=conn)

    correct = 0
    for row in rows:
        is_correct = 1 if row["selected_option"] == row["correct_option"] else 0
        correct += is_correct
        conn.execute("UPDATE user_answers SET is_correct = ? WHERE id = ?", (is_correct, row["id"]))

    total = len(rows)
    score = round(correct / total * 100, 1) if total else 0.0
    taken = int(min(max(elapsed, 0), limit_seconds))

    cursor = conn.execute(
        """UPDATE test_attempts
           SET status = 'submitted', submitted_at = ?, total_questions = ?, correct_count = ?,
               score_percent = ?, time_taken_seconds = ?
           WHERE id = ? AND status = 'in_progress'""",
        (to_db_time(now), total, correct, score, taken, attempt_id))
    closed = cursor.rowcount == 1
    conn.commit()
    return closed


def finalize_expired_attempts(user_id):
    """Score every in-progress attempt of this user whose time is over. Returns how many."""
    rows = db.query_db(
        """SELECT a.id, a.started_at, t.duration_minutes
           FROM test_attempts a JOIN mock_tests t ON t.id = a.mock_test_id
           WHERE a.user_id = ? AND a.status = 'in_progress'""", (user_id,))
    count = 0
    for row in rows:
        if seconds_remaining(row, row["duration_minutes"]) <= 0:
            if finalize_attempt(row["id"], row["duration_minutes"]):
                count += 1
    return count