"""check_tests.py - tests the mock test system and the user dashboard."""
import html as htmllib
import json
import os
import re
import tempfile
from datetime import timedelta

from werkzeug.security import generate_password_hash

import mock_engine
import seed_data
from app import create_app
from db import standalone_db, query_db, execute_db, create_user

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def flat(response):
    return " ".join(response.get_data(as_text=True).split())


def test_data_from(response):
    match = re.search(r'<script type="application/json" id="test-data">(.*?)</script>',
                      response.get_data(as_text=True), re.S)
    return json.loads(match.group(1)) if match else None


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        app = create_app({"DATABASE_PATH": db_path, "UPLOAD_FOLDER": os.path.join(tmp, "uploads"),
                          "WTF_CSRF_ENABLED": False, "TESTING": True})

        def sql(query, args=()):
            with standalone_db(db_path) as conn:
                return query_db(query, args, conn=conn)

        def sql_one(query, args=()):
            rows = sql(query, args)
            return rows[0] if rows else None

        def run(query, args=()):
            with standalone_db(db_path) as conn:
                execute_db(query, args, conn=conn)

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)
            seed_data.seed_demo_user(conn)
            create_user("Other Student", "other@example.com", generate_password_hash("Other@1234"),
                        "2000-01-01", "Graduate (Bachelor's Degree)", "Andhra Pradesh", "Guntur", conn=conn)

        def find_test(code, subject):
            return sql_one("""SELECT t.* FROM mock_tests t
                              JOIN exams e ON e.id = t.exam_id JOIN subjects s ON s.id = t.subject_id
                              WHERE e.short_code = ? AND s.name = ?""", (code, subject))

        ga = find_test("SSC-CGL", "General Awareness")
        quant = find_test("SSC-CGL", "Quantitative Aptitude")
        rrb = find_test("RRB-NTPC", "Mathematics")
        appsc = find_test("APPSC-G2", "General Studies")
        polity = find_test("UPSC-CSE", "Indian Polity")
        demo = sql_one("SELECT id FROM users WHERE email = 'demo@example.com'")

        def start(client, test_id):
            r = client.post(f"/mock-tests/{test_id}/start")
            m = re.search(r"/attempts/(\d+)/take", r.headers.get("Location", ""))
            return r, (int(m.group(1)) if m else None)

        def age_attempt(attempt_id, seconds):
            started = mock_engine.to_db_time(mock_engine.utc_now() - timedelta(seconds=seconds))
            run("UPDATE test_attempts SET started_at = ? WHERE id = ?", (started, attempt_id))

        def attempt_row(attempt_id):
            return sql_one("SELECT * FROM test_attempts WHERE id = ?", (attempt_id,))

        def attempt_questions(attempt_id):
            return sql("""SELECT ua.question_id, q.correct_option, q.explanation
                          FROM user_answers ua JOIN questions q ON q.id = ua.question_id
                          WHERE ua.attempt_id = ? ORDER BY ua.question_order""", (attempt_id,))

        # ================= Public pages and login protection =================
        client = app.test_client()
        r = client.get("/mock-tests")
        html = flat(r)
        check("Mock test list loads", r.status_code == 200 and "SSC-CGL - General Awareness Practice Test" in html)
        check("Demo-question disclaimer is shown", "original practice questions created for demonstration" in html)
        check("External official mock tests are clearly not hosted here", "does not host" in html)
        html = flat(client.get(f"/mock-tests?exam={rrb['exam_id']}"))
        check("List filter by exam", "RRB-NTPC - Mathematics" in html and "SSC-CGL - General Awareness" not in html)
        check("Invalid exam filter is ignored", client.get("/mock-tests?exam=abc").status_code == 200)

        r, _ = start(client, ga["id"])
        check("Starting while logged out redirects to login", r.status_code == 302 and "/login" in r.headers["Location"])
        check("Test page needs login", client.get("/attempts/1/take").status_code == 302)
        check("History needs login", client.get("/attempt-history").status_code == 302)
        check("Dashboard needs login", client.get("/dashboard").status_code == 302)
        check("Autosave while logged out gives 401", client.post("/attempts/1/answer", json={}).status_code == 401)

        r = client.post("/login", data={"email": "demo@example.com", "password": "Demo@1234"})
        check("Login now lands on the dashboard", r.status_code == 302 and r.headers["Location"].endswith("/dashboard"))

        # ================= Start a test =================
        r, a1 = start(client, ga["id"])
        check("Start redirects to the test page", r.status_code == 302 and a1 is not None)
        rows = attempt_questions(a1)
        check("10 questions are chosen for the attempt", len(rows) == 10 and len({x["question_id"] for x in rows}) == 10)
        outside = sql_one("""SELECT COUNT(*) AS c FROM user_answers ua JOIN questions q ON q.id = ua.question_id
                             WHERE ua.attempt_id = ? AND q.subject_id != ?""", (a1, ga["subject_id"]))["c"]
        check("All questions belong to the test's subject", outside == 0)
        check("Attempt starts as in_progress", attempt_row(a1)["status"] == "in_progress")

        r = client.get(f"/attempts/{a1}/take")
        data = test_data_from(r)
        page = r.get_data(as_text=True)
        check("Test page loads with question data", r.status_code == 200 and data and len(data["questions"]) == 10)
        check("Timer value is sent from the server", data and 0 < data["remainingSeconds"] <= 600)
        check("Questions have no answer fields", data and all(set(q) == {"id", "number", "text", "options"} for q in data["questions"]))
        check("Correct answers and explanations are not in the page",
              "correct_option" not in page and rows[0]["explanation"] not in page)

        # ================= Autosave =================
        q0 = data["questions"][0]["id"]
        r = client.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": "B"})
        check("Autosave works", r.status_code == 200 and r.get_json()["ok"])
        check("Selection is stored", sql_one("SELECT selected_option AS s FROM user_answers WHERE attempt_id = ? AND question_id = ?", (a1, q0))["s"] == "B")
        client.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": "C"})
        data = test_data_from(client.get(f"/attempts/{a1}/take"))
        check("Reload restores the saved answer", data["answers"].get(str(q0)) == "C")
        client.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": None})
        check("Clearing an answer works", sql_one("SELECT selected_option AS s FROM user_answers WHERE attempt_id = ? AND question_id = ?", (a1, q0))["s"] is None)
        check("Invalid option is rejected", client.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": "Z"}).status_code == 400)
        check("Invalid question id type is rejected", client.post(f"/attempts/{a1}/answer", json={"question_id": "abc", "option": "A"}).status_code == 400)
        check("Question from another test is rejected", client.post(f"/attempts/{a1}/answer", json={"question_id": 999999, "option": "A"}).status_code == 404)
        check("Non-JSON body is rejected", client.post(f"/attempts/{a1}/answer", data="x").status_code == 400)

        # ================= Another user cannot touch this attempt =================
        other = app.test_client()
        other.post("/login", data={"email": "other@example.com", "password": "Other@1234"})
        check("Other user cannot open the test", other.get(f"/attempts/{a1}/take").status_code == 404)
        check("Other user cannot save answers", other.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": "A"}).status_code == 404)
        check("Other user cannot submit it", other.post(f"/attempts/{a1}/submit", data={}).status_code == 404)
        check("Other user cannot see results", other.get(f"/attempts/{a1}/results").status_code == 404)

        # ================= Resume =================
        r, again = start(client, ga["id"])
        check("Starting the same test resumes it", again == a1)
        check("Only one in-progress attempt exists",
              sql_one("SELECT COUNT(*) AS c FROM test_attempts WHERE user_id = ? AND mock_test_id = ? AND status = 'in_progress'", (demo["id"], ga["id"]))["c"] == 1)
        check("Results are not available before submitting", client.get(f"/attempts/{a1}/results").status_code == 302)

        # ================= Submit and scoring =================
        answers = {}
        for i, row in enumerate(rows):
            if i < 6:
                answers[str(row["question_id"])] = row["correct_option"]          # 6 correct
            elif i < 8:
                answers[str(row["question_id"])] = "A" if row["correct_option"] != "A" else "B"   # 2 wrong
            elif i == 8:
                answers[str(row["question_id"])] = None                          # unanswered
        r = client.post(f"/attempts/{a1}/submit", data={"answers": json.dumps(answers)})
        check("Submit redirects to results", r.status_code == 302 and f"/attempts/{a1}/results" in r.headers["Location"])
        done = attempt_row(a1)
        check("Attempt is marked submitted", done["status"] == "submitted" and done["submitted_at"])
        check("Score is calculated on the server: 6 of 10 = 60%",
              done["correct_count"] == 6 and done["total_questions"] == 10 and done["score_percent"] == 60.0)
        check("Time taken is saved", done["time_taken_seconds"] is not None and done["time_taken_seconds"] < 600)
        flags = sql("SELECT is_correct FROM user_answers WHERE attempt_id = ?", (a1,))
        check("Each answer has is_correct saved", sum(f["is_correct"] for f in flags) == 6 and all(f["is_correct"] is not None for f in flags))

        r = client.get(f"/attempts/{a1}/results")
        page = htmllib.unescape(flat(r))
        check("Results page loads with the score", r.status_code == 200 and "6 out of 10 correct" in page and "60%" in page)
        check("Results show correct answers and explanations", "Correct answer" in page and rows[0]["explanation"] in page)
        check("Results show incorrect and unanswered counts", "Incorrect" in page and "Unanswered" in page and "(Your answer)" in page)

        r = client.post(f"/attempts/{a1}/submit", data={"answers": json.dumps({str(x["question_id"]): x["correct_option"] for x in rows})})
        check("A second submit cannot change the score", attempt_row(a1)["correct_count"] == 6)
        check("Autosave after submit is refused (409)", client.post(f"/attempts/{a1}/answer", json={"question_id": q0, "option": "A"}).status_code == 409)
        check("Test page redirects to results once submitted", "/results" in client.get(f"/attempts/{a1}/take").headers["Location"])

        # ================= Tampering with the submit form =================
        r, a2 = start(client, quant["id"])
        weird = {"999999": "A", str(attempt_questions(a2)[0]["question_id"]): "Z", "abc": "A", "1e3": "B"}
        r = client.post(f"/attempts/{a2}/submit", data={"answers": json.dumps(weird)})
        check("Tampered answers are ignored, no crash", r.status_code == 302 and attempt_row(a2)["correct_count"] == 0)
        check("No invalid option was stored", sql_one("SELECT COUNT(*) AS c FROM user_answers WHERE attempt_id = ? AND selected_option IS NOT NULL", (a2,))["c"] == 0)
        r, a3 = start(client, rrb["id"])
        r = client.post(f"/attempts/{a3}/submit", data={"answers": "not json{"})
        check("Invalid JSON in the submit form is handled", r.status_code == 302 and attempt_row(a3)["status"] == "submitted")

        # ================= The timer is enforced by the server =================
        r, a4 = start(client, ga["id"])
        age_attempt(a4, 3600)
        check("Autosave after the deadline is refused", client.post(f"/attempts/{a4}/answer", json={"question_id": attempt_questions(a4)[0]["question_id"], "option": "A"}).status_code == 409)
        q4 = attempt_questions(a4)
        client.post(f"/attempts/{a4}/submit", data={"answers": json.dumps({str(x["question_id"]): x["correct_option"] for x in q4})})
        check("Answers sent long after the deadline are not counted", attempt_row(a4)["correct_count"] == 0)

        r, a5 = start(client, ga["id"])
        q5 = attempt_questions(a5)
        client.post(f"/attempts/{a5}/answer", json={"question_id": q5[0]["question_id"], "option": q5[0]["correct_option"]})
        age_attempt(a5, 601)
        r = client.get(f"/attempts/{a5}/take", follow_redirects=True)
        done = attempt_row(a5)
        check("Opening an expired test submits it automatically", done["status"] == "submitted" and "Time is up" in flat(r))
        check("Auto-submit scores the answers saved so far", done["correct_count"] == 1)

        r, a6 = start(client, ga["id"])
        q6 = attempt_questions(a6)
        age_attempt(a6, 610)
        client.post(f"/attempts/{a6}/submit", data={"answers": json.dumps({str(x["question_id"]): x["correct_option"] for x in q6[:3]})})
        check("Submit within the grace period after 0:00 still counts", attempt_row(a6)["correct_count"] == 3)

        r, a7 = start(client, ga["id"])
        age_attempt(a7, 5000)
        client.get("/mock-tests")
        check("Expired attempts are closed when the list is opened", attempt_row(a7)["status"] == "submitted")

        # ================= Question count and edge cases =================
        run("UPDATE mock_tests SET num_questions = 3 WHERE id = ?", (rrb["id"],))
        r, a8 = start(client, rrb["id"])
        check("num_questions limits the number of questions", len(attempt_questions(a8)) == 3)
        client.post(f"/attempts/{a8}/submit", data={})
        check("Submitting with no answers scores 0", attempt_row(a8)["score_percent"] == 0.0)

        ex = sql_one("SELECT id FROM exams WHERE short_code = 'SSC-CGL'")
        run("INSERT INTO subjects (exam_id, name) VALUES (?, 'Empty Subject')", (ex["id"],))
        sid = sql_one("SELECT id FROM subjects WHERE name = 'Empty Subject'")["id"]
        run("INSERT INTO mock_tests (title, exam_id, subject_id) VALUES ('Empty Test', ?, ?)", (ex["id"], sid))
        empty = sql_one("SELECT id FROM mock_tests WHERE title = 'Empty Test'")
        r = client.post(f"/mock-tests/{empty['id']}/start", follow_redirects=True)
        check("A test with no questions cannot be started", "has no questions yet" in flat(r))
        check("No attempt row is created for it", sql_one("SELECT COUNT(*) AS c FROM test_attempts WHERE mock_test_id = ?", (empty["id"],))["c"] == 0)

        run("UPDATE mock_tests SET is_active = 0 WHERE id = ?", (polity["id"],))
        check("An inactive test cannot be started", client.post(f"/mock-tests/{polity['id']}/start").status_code == 404)
        check("Inactive tests are hidden from the list", "Indian Polity Practice Test" not in flat(client.get("/mock-tests")))
        check("Unknown test gives 404", client.post("/mock-tests/99999/start").status_code == 404)

        # ================= History =================
        r, a9 = start(client, appsc["id"])      # left in progress on purpose
        r = client.get("/attempt-history")
        html = flat(r)
        check("History page loads", r.status_code == 200 and "Average score" in html and "View result" in html)
        check("History shows the in-progress attempt with Resume", "In progress" in html and "Resume" in html)
        html = flat(client.get(f"/attempt-history?exam={ga['exam_id']}"))
        check("History filter by exam", "SSC-CGL - General Awareness" in html and "RRB-NTPC - Mathematics" not in html)
        check("Invalid history filters are handled", client.get("/attempt-history?page=abc&exam=x").status_code == 200)
        check("Test list shows the best score", "Best score" in flat(client.get("/mock-tests")))
        check("Test list shows Resume for the open attempt", "Resume test" in flat(client.get("/mock-tests")))

        # ================= Dashboard =================
        client.post("/jobs/%d/save" % sql_one("SELECT id FROM jobs WHERE title LIKE '%Auditor%'")["id"], data={"next": "/dashboard"})
        r = client.get("/dashboard")
        html = flat(r)
        check("Dashboard loads with a welcome message", r.status_code == 200 and "Welcome, Demo" in html)
        for heading in ["Jobs matching your profile", "Latest job notifications", "Upcoming application deadlines",
                        "Saved jobs", "Recent mock tests", "Preparation progress", "Average mock test score", "Your profile"]:
            check(f"Dashboard shows '{heading}'", heading in html)
        check("Dashboard lists an eligible open job", "Auditor" in html)
        check("Dashboard offers to continue the open test", "Continue your test" in html)
        check("Dashboard shows the score chart after 2+ tests", "scoreChart" in r.get_data(as_text=True))
        check("Other user's dashboard shows no attempts", "No tests taken yet" in flat(other.get("/dashboard")))

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()