"""test_workflows.py - end-to-end test of the 16 required workflows.
CSRF protection stays ON: every form post sends a real token, like a browser."""
import html as htmllib
import io
import json
import re
import os
import tempfile
from datetime import date

import create_admin
import seed_data
from app import create_app
from db import standalone_db, query_db

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def step(number, title):
    print(f"\n--- Workflow {number}: {title}")


def flat(response):
    """Page text with whitespace collapsed and HTML entities decoded."""
    return htmllib.unescape(" ".join(response.get_data(as_text=True).split()))


def token(client):
    page = client.get("/").get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', page)
    return match.group(1) if match else ""


def post(client, url, data=None, **kwargs):
    payload = dict(data or {})
    payload["csrf_token"] = token(client)
    return client.post(url, data=payload, **kwargs)


def attempt_id_from(response):
    match = re.search(r"/attempts/(\d+)/take", response.headers.get("Location", ""))
    return int(match.group(1)) if match else None


def test_data_from(response):
    match = re.search(r'<script type="application/json" id="test-data">(.*?)</script>',
                      response.get_data(as_text=True), re.S)
    return json.loads(match.group(1)) if match else None


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        upload = os.path.join(tmp, "uploads")
        app = create_app({"DATABASE_PATH": db_path, "UPLOAD_FOLDER": upload, "TESTING": True})

        def sql(query, args=()):
            with standalone_db(db_path) as conn:
                return query_db(query, args, conn=conn)

        def one(query, args=()):
            rows = sql(query, args)
            return rows[0] if rows else None

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)
            create_admin.create_admin(conn, "Workflow Admin", "wfadmin@example.com", "Admin@1234")

        auditor = one("SELECT id FROM jobs WHERE title LIKE '%Auditor%'")
        station = one("SELECT id FROM jobs WHERE title LIKE '%Station Master%'")
        ssc = one("SELECT id FROM exams WHERE short_code = 'SSC-CGL'")["id"]
        chsl = one("SELECT id FROM exams WHERE short_code = 'SSC-CHSL'")["id"]
        ga_test = one("""SELECT t.* FROM mock_tests t JOIN exams e ON e.id = t.exam_id
                         JOIN subjects s ON s.id = t.subject_id
                         WHERE e.short_code = 'SSC-CGL' AND s.name = 'General Awareness'""")

        today = date.today()
        dob = date(today.year - 24, today.month, min(today.day, 28)).isoformat()
        student = app.test_client()

        # ============================================================
        step(1, "Register a new user")
        reg = {"full_name": "Workflow Student", "email": "Workflow@Example.com", "password": "Work@1234",
               "confirm_password": "Work@1234", "date_of_birth": dob,
               "highest_qualification": "Graduate (Bachelor's Degree)", "state": "Andhra Pradesh",
               "district": "Guntur", "preferred_category": "SSC"}
        r = post(student, "/register", {**reg, "password": "short", "confirm_password": "short"})
        check("A weak password is rejected", r.status_code == 200 and "at least 8 characters" in flat(r))
        r = post(student, "/register", reg)
        check("Registration redirects to the login page", r.status_code == 302 and "/login" in r.headers["Location"])
        user = one("SELECT * FROM users WHERE email = 'workflow@example.com'")
        check("The user is saved with a lower-case email and the 'user' role", user is not None and user["role"] == "user")
        check("The password is stored as a hash", user["password_hash"] != "Work@1234"
              and user["password_hash"].startswith(("scrypt:", "pbkdf2:")))
        r = post(student, "/register", reg)
        check("Registering the same email again is rejected", r.status_code == 200 and "already exists" in flat(r))

        # ============================================================
        step(2, "Log in and log out")
        r = post(student, "/login", {"email": "workflow@example.com", "password": "wrong-pass1"})
        check("A wrong password shows an error", r.status_code == 200 and "Invalid email or password" in flat(r))
        r = post(student, "/login", {"email": "workflow@example.com", "password": "Work@1234"})
        check("Login succeeds and goes to the dashboard", r.status_code == 302 and r.headers["Location"].endswith("/dashboard"))
        r = student.get("/dashboard")
        check("The protected dashboard shows a welcome message", r.status_code == 200 and "Welcome, Workflow" in flat(r))
        r = post(student, "/logout")
        with student.session_transaction() as s:
            gone = "user_id" not in s
        check("Logout clears the session", r.status_code == 302 and gone)
        check("The dashboard is protected after logout", student.get("/dashboard").status_code == 302)
        post(student, "/login", {"email": "workflow@example.com", "password": "Work@1234"})

        # ============================================================
        step(3, "Update the user profile")
        check("The profile page shows the user", "Workflow Student" in flat(student.get("/profile")))
        profile = {k: reg[k] for k in ("full_name", "date_of_birth", "highest_qualification", "state",
                                       "district", "preferred_category")}
        r = post(student, "/profile", {**profile, "action": "update_profile", "district": "Vijayawada"})
        check("A valid profile update is saved", r.status_code == 302
              and one("SELECT district FROM users WHERE id = ?", (user["id"],))["district"] == "Vijayawada")
        r = post(student, "/profile", {**profile, "action": "update_profile", "date_of_birth": "2999-01-01"})
        check("A future date of birth is rejected", r.status_code == 200 and "cannot be in the future" in flat(r))

        # ============================================================
        step(4, "Search and filter government jobs")
        html = flat(student.get("/jobs?q=clerk"))
        check("Search by title finds clerk posts", "Lower Division Clerk" in html and "Station Master" not in html)
        html = flat(student.get("/jobs?govt=Andhra+Pradesh"))
        check("Filter: Andhra Pradesh jobs only", "Group-II Executive" in html and "Station Master" not in html)
        html = flat(student.get("/jobs?category=Railway"))
        check("Filter: Railway category", "Station Master" in html and "Auditor" not in html)
        html = flat(student.get("/jobs?qualification=1"))
        check("Filter: qualification level", "Multi Tasking Staff" in html and "Auditor" not in html)
        html = flat(student.get("/jobs?deadline=closed"))
        check("Filter: closed deadlines", "Track Maintainer" in html and "Station Master" not in html)
        html = flat(student.get("/jobs?sort=deadline_desc"))
        check("Sort: latest deadline first", 0 <= html.find("Multi Tasking Staff") < html.find("Statistical Investigator"))

        # ============================================================
        step(5, "Open a job details page")
        r = student.get(f"/jobs/{auditor['id']}")
        html = flat(r)
        check("The job details page loads", r.status_code == 200 and "Auditor" in html)
        check("Demo data is clearly labelled", "Demonstration record" in html)
        check("The official application link opens in a new tab", 'target="_blank"' in r.get_data(as_text=True)
              and "Apply on official website" in html)
        check("An unknown job gives a 404 page", student.get("/jobs/99999").status_code == 404)

        # ============================================================
        step(6, "Check eligibility")
        html = flat(student.get(f"/jobs/{auditor['id']}"))
        check("Job details show the user's own eligibility with reasons",
              "Your eligibility" in html and "Qualification matches" in html and "Age appears to be within" in html)
        html = flat(student.get("/eligibility?use_profile=1"))
        check("'Use my profile' runs the checker", "using your profile" in html and "Jobs checked" in html)
        check("The official-notification disclaimer is shown",
              "must be verified using the official recruitment notification" in html)
        html = flat(student.get("/eligibility?age=24&qualification=1&state=Andhra+Pradesh&show=not_eligible"))
        check("A 10th-pass profile is not eligible for graduate posts, with a reason",
              "Qualification requirement not satisfied" in html)
        html = flat(student.get("/eligibility?age=30&qualification=4&state=Andhra+Pradesh&show=verify"))
        check("An over-age profile needs verification and relaxation is not assumed",
              "age relaxation" in html and "Needs further verification" in html)

        # ============================================================
        step(7, "Save a job")
        r = post(student, f"/jobs/{auditor['id']}/save", {"next": "/jobs"})
        check("Saving redirects back to the list", r.status_code == 302 and r.headers["Location"].endswith("/jobs"))
        check("The bookmark is stored in the database",
              one("SELECT id FROM saved_jobs WHERE user_id = ? AND job_id = ?", (user["id"], auditor["id"])) is not None)
        check("The Saved Jobs page lists it", "Auditor" in flat(student.get("/saved-jobs")))
        post(student, f"/jobs/{station['id']}/save", {"next": "/jobs"})
        post(student, f"/jobs/{station['id']}/save", {"next": "/jobs"})
        check("Clicking the bookmark again removes it",
              one("SELECT id FROM saved_jobs WHERE user_id = ? AND job_id = ?", (user["id"], station["id"])) is None)

        # ============================================================
        step(8, "Open study materials")
        r = student.get("/materials")
        raw = r.get_data(as_text=True)
        check("The materials page lists official resources", r.status_code == 200 and "NCERT Textbooks (free, official)" in raw)
        check("Each resource has a working external link that opens in a new tab",
              'href="https://ncert.nic.in/textbook.php"' in raw and 'rel="noopener noreferrer"' in raw)
        check("Official and additional resources are distinguished", "Official" in raw)
        check("Materials can be filtered by subject", "SSC Syllabus (official)" in flat(
            student.get("/materials?subject=%d" % one(
                "SELECT s.id FROM subjects s WHERE s.name = 'General Awareness' AND s.exam_id = ?", (ssc,))["id"])))

        # ============================================================
        step(9, "Access previous-paper links")
        r = student.get("/previous-papers")
        raw = r.get_data(as_text=True)
        check("Previous papers page loads", r.status_code == 200 and "UPSC previous question papers" in raw)
        check("The official UPSC link is present", "https://www.upsc.gov.in/examinations/previous-question-papers" in raw)
        check("The official APPSC link is present", "https://portal-psc.ap.gov.in/HomePages/GroupsSyllabus" in raw)

        # ============================================================
        step(10, "Start and submit a mock test")
        check("The test is listed", "SSC-CGL - General Awareness Practice Test" in flat(student.get("/mock-tests")))
        r = post(student, f"/mock-tests/{ga_test['id']}/start")
        attempt = attempt_id_from(r)
        check("Starting a test redirects to the test page", r.status_code == 302 and attempt is not None)
        page = student.get(f"/attempts/{attempt}/take")
        data = test_data_from(page)
        check("The test page has 10 questions and a server-side timer",
              data and len(data["questions"]) == 10 and 0 < data["remainingSeconds"] <= 600)
        check("Correct answers are not sent to the browser during the test",
              "correct_option" not in page.get_data(as_text=True))
        rows = sql("""SELECT ua.question_id, q.correct_option, q.explanation FROM user_answers ua
                      JOIN questions q ON q.id = ua.question_id WHERE ua.attempt_id = ?
                      ORDER BY ua.question_order""", (attempt,))
        ok = True
        for row in rows[:3]:                      # autosave (like a click in the browser)
            r = student.post(data["saveUrl"], json={"question_id": row["question_id"], "option": row["correct_option"]},
                             headers={"X-CSRFToken": token(student)})
            ok = ok and r.status_code == 200 and r.get_json()["ok"]
        check("Answers autosave while the test is running", ok)
        answers = {str(row["question_id"]): row["correct_option"] for row in rows[:7]}   # 7 correct, 3 unanswered
        r = post(student, f"/attempts/{attempt}/submit", {"answers": json.dumps(answers)})
        check("Submitting redirects to the results page", r.status_code == 302 and "/results" in r.headers["Location"])
        r = student.post(f"/attempts/{attempt}/submit", data={"answers": "{}"})
        check("A submit without a CSRF token is rejected", r.status_code == 302 and "/results" not in r.headers["Location"])

        # ============================================================
        step(11, "View the score and explanations")
        r = student.get(f"/attempts/{attempt}/results")
        html = flat(r)
        check("The result page shows the server-calculated score", r.status_code == 200
              and "7 out of 10 correct" in html and "70%" in html)
        check("Correct answers and explanations are shown after submission",
              "Correct answer" in html and htmllib.unescape(rows[0]["explanation"]) in html)
        check("Unanswered questions are counted", "Unanswered" in html)

        # ============================================================
        step(12, "Verify that the attempt is saved")
        saved = one("SELECT * FROM test_attempts WHERE id = ?", (attempt,))
        check("The attempt is stored as submitted with the right score",
              saved["status"] == "submitted" and saved["correct_count"] == 7 and saved["score_percent"] == 70.0
              and saved["total_questions"] == 10 and saved["time_taken_seconds"] is not None)
        flags = sql("SELECT is_correct FROM user_answers WHERE attempt_id = ?", (attempt,))
        check("All 10 answers are stored with their marking", len(flags) == 10 and sum(f["is_correct"] for f in flags) == 7)
        check("The history page lists the attempt", "View result" in flat(student.get("/attempt-history")))
        check("The dashboard shows the average score", "70%" in flat(student.get("/dashboard")))

        # ============================================================
        step(13, "Log in as an administrator")
        admin = app.test_client()
        r = post(admin, "/login", {"email": "wfadmin@example.com", "password": "Admin@1234"})
        check("The admin can log in", r.status_code == 302)
        r = admin.get("/admin")
        check("The admin panel opens", r.status_code == 200 and "Admin Panel" in flat(r) and "Registered users" in flat(r))
        check("The navbar shows the Admin Panel link", "Admin Panel" in admin.get("/").get_data(as_text=True))

        # ============================================================
        step(14, "Add and edit a job")
        job_form = {"title": "Workflow Test Clerk", "organization": "Test Org", "govt_category": "Central",
                    "exam_category": "SSC", "min_qualification_level": "2", "required_qualification": "12th pass",
                    "min_age": "18", "max_age": "27", "state_requirement": "", "vacancies": "50", "vacancies_note": "",
                    "application_start": "2026-01-01", "application_deadline": "2099-12-31", "salary": "First pay",
                    "description": "Test description", "eligibility_text": "Test eligibility",
                    "syllabus_pattern": "Test pattern", "notification_url": "https://ssc.gov.in/",
                    "apply_url": "https://ssc.gov.in/", "is_demo": "1", "exam_ids": [str(ssc), str(chsl)]}
        r = post(admin, "/admin/jobs/new", {**job_form, "apply_url": "javascript:alert(1)"})
        check("A javascript: link is rejected", r.status_code == 200 and "full http" in flat(r))
        r = post(admin, "/admin/jobs/new", job_form)
        job = one("SELECT * FROM jobs WHERE title = 'Workflow Test Clerk'")
        check("A valid job is added", r.status_code == 302 and job is not None and job["is_demo"] == 1)
        check("The job is linked to both exams", len(sql("SELECT * FROM job_exams WHERE job_id = ?", (job["id"],))) == 2)
        check("Students can find the new job", "Workflow Test Clerk" in flat(student.get("/jobs?q=Workflow+Test")))
        r = post(admin, f"/admin/jobs/{job['id']}/edit", {**job_form, "salary": "Edited pay"})
        check("The job can be edited", r.status_code == 302 and "Edited pay" in flat(student.get(f"/jobs/{job['id']}")))

        # ============================================================
        step(15, "Add study material and mock-test questions")
        r = post(admin, "/admin/subjects/save", {"exam_id": ssc, "name": "Workflow Subject", "description": "for the test"})
        subject = one("SELECT * FROM subjects WHERE name = 'Workflow Subject'")
        check("A subject is added", r.status_code == 302 and subject is not None)
        material = {"subject_id": subject["id"], "title": "Workflow Notes", "description": "uploaded in the test",
                    "resource_type": "PDF", "url": "", "file": (io.BytesIO(b"%PDF-1.4\n%workflow\n"), "notes.pdf")}
        r = post(admin, "/admin/materials/new", material, content_type="multipart/form-data")
        mat = one("SELECT * FROM study_materials WHERE title = 'Workflow Notes'")
        check("A PDF study material is uploaded", r.status_code == 302 and mat and mat["file_path"] in os.listdir(upload))
        r = student.get(f"/materials/{mat['id']}/file")
        check("Students can open the uploaded PDF", r.status_code == 200 and r.data.startswith(b"%PDF-"))
        check("Students see it in the materials list", "Workflow Notes" in flat(student.get(f"/materials?subject={subject['id']}")))
        fake = {"subject_id": subject["id"], "title": "Fake", "resource_type": "PDF", "url": "",
                "file": (io.BytesIO(b"not a pdf"), "fake.pdf")}
        r = post(admin, "/admin/materials/new", fake, content_type="multipart/form-data")
        check("A fake PDF is rejected", r.status_code == 200 and "not a valid PDF" in flat(r))

        for text, options, correct in [("Workflow question one?", ["a1", "a2", "a3", "a4"], "B"),
                                       ("Workflow question two?", ["b1", "b2", "b3", "b4"], "D")]:
            post(admin, "/admin/questions/new", {
                "subject_id": subject["id"], "question_text": text, "option_a": options[0], "option_b": options[1],
                "option_c": options[2], "option_d": options[3], "correct_option": correct,
                "explanation": "Because of the workflow test.", "difficulty": "Easy", "is_demo": "1"})
        check("Two questions are added", one("SELECT COUNT(*) AS c FROM questions WHERE subject_id = ?", (subject["id"],))["c"] == 2)
        check("Students can see the new questions",
              "Workflow question one?" in flat(student.get(f"/practice-questions?subject={subject['id']}")))
        post(admin, "/admin/mock-tests/save", {"subject_id": subject["id"], "title": "Workflow Test Quiz",
                                               "duration_minutes": "5", "num_questions": "2", "is_active": "1"})
        new_test = one("SELECT * FROM mock_tests WHERE subject_id = ?", (subject["id"],))
        check("A mock test is created for the subject", new_test is not None)
        check("Students see the new test", "Workflow Test Quiz" in flat(student.get("/mock-tests")))
        r = post(student, f"/mock-tests/{new_test['id']}/start")
        attempt2 = attempt_id_from(r)
        rows2 = sql("""SELECT ua.question_id, q.correct_option FROM user_answers ua JOIN questions q ON q.id = ua.question_id
                       WHERE ua.attempt_id = ?""", (attempt2,))
        check("The admin-made test serves the admin-made questions", len(rows2) == 2)
        post(student, f"/attempts/{attempt2}/submit",
             {"answers": json.dumps({str(x["question_id"]): x["correct_option"] for x in rows2})})
        check("Answering both correctly scores 100%", "100%" in flat(student.get(f"/attempts/{attempt2}/results")))

        # ============================================================
        step(16, "Normal users cannot use admin functions")
        pages = ["/admin", "/admin/users", "/admin/jobs", "/admin/jobs/new", "/admin/exams", "/admin/subjects",
                 "/admin/materials/new", "/admin/papers", "/admin/resources", "/admin/mock-tests",
                 "/admin/questions/new", "/admin/results"]
        check("A normal user gets 403 on every admin page", all(student.get(p).status_code == 403 for p in pages))
        r = post(student, f"/admin/jobs/{job['id']}/delete")
        check("A normal user cannot delete a job", r.status_code == 403 and one("SELECT id FROM jobs WHERE id = ?", (job["id"],)))
        r = post(student, f"/admin/users/{user['id']}/role", {"role": "admin"})
        check("A normal user cannot make themselves an admin",
              r.status_code == 403 and one("SELECT role FROM users WHERE id = ?", (user["id"],))["role"] == "user")
        check("The Admin Panel link is hidden from normal users", "Admin Panel" not in student.get("/").get_data(as_text=True))
        anonymous = app.test_client()
        r = anonymous.get("/admin")
        check("An anonymous visitor is sent to the login page", r.status_code == 302 and "/login" in r.headers["Location"])
        r = admin.post(f"/admin/jobs/{job['id']}/delete")
        check("Even an admin's POST without a CSRF token is rejected",
              r.status_code == 302 and one("SELECT id FROM jobs WHERE id = ?", (job["id"],)) is not None)
        check("The database has no broken relationships", not sql("PRAGMA foreign_key_check"))

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()