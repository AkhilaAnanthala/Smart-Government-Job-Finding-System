"""check_admin.py - tests create_admin.py and the whole admin area."""
import io
import os
import tempfile

import create_admin
import mock_engine
import seed_data
from app import create_app
from db import standalone_db, query_db, execute_db, create_user
from werkzeug.security import generate_password_hash

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def flat(response):
    return " ".join(response.get_data(as_text=True).split())


def pdf(content=b"%PDF-1.4\n%test\n", name="notes.pdf"):
    return (io.BytesIO(content), name)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        upload = os.path.join(tmp, "uploads")
        app = create_app({"DATABASE_PATH": db_path, "UPLOAD_FOLDER": upload,
                          "WTF_CSRF_ENABLED": False, "TESTING": True})

        def sql(query, args=()):
            with standalone_db(db_path) as conn:
                return query_db(query, args, conn=conn)

        def one(query, args=()):
            rows = sql(query, args)
            return rows[0] if rows else None

        def run(query, args=()):
            with standalone_db(db_path) as conn:
                execute_db(query, args, conn=conn)

        def files():
            return sorted(os.listdir(upload))

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)
            seed_data.seed_demo_user(conn)

            # ================= create_admin.py =================
            for label, args in [("weak password", ("Ada Admin", "ada@example.com", "short")),
                                ("password without a number", ("Ada Admin", "ada@example.com", "onlyletters")),
                                ("invalid email", ("Ada Admin", "not-an-email", "Admin@1234")),
                                ("invalid name", ("A", "ada@example.com", "Admin@1234"))]:
                try:
                    create_admin.create_admin(conn, *args)
                    check(f"create_admin rejects {label}", False)
                except ValueError:
                    check(f"create_admin rejects {label}", True)
            create_admin.create_admin(conn, "Admin User", "Admin@Example.com", "Admin@1234")
            try:
                create_admin.create_admin(conn, "Admin Two", "admin@example.com", "Admin@1234")
                check("create_admin rejects a duplicate email", False)
            except ValueError:
                check("create_admin rejects a duplicate email", True)
            create_user("Plain Student", "plain@example.com", generate_password_hash("Plain@1234"),
                        "2000-01-01", "Graduate (Bachelor's Degree)", "Andhra Pradesh", "Guntur", conn=conn)
            create_admin.promote_to_admin(conn, "plain@example.com")
            for label, email in [("promote an unknown email", "nobody@example.com"),
                                 ("promote someone who is already admin", "plain@example.com")]:
                try:
                    create_admin.promote_to_admin(conn, email)
                    check(f"Cannot {label}", False)
                except ValueError:
                    check(f"Cannot {label}", True)

        admin_row = one("SELECT * FROM users WHERE email = 'admin@example.com'")
        check("Admin account exists with the admin role", admin_row is not None and admin_row["role"] == "admin")
        check("Admin password is stored hashed", admin_row["password_hash"] != "Admin@1234"
              and admin_row["password_hash"].startswith(("scrypt:", "pbkdf2:")))
        check("Promoted account has the admin role", one("SELECT role FROM users WHERE email = 'plain@example.com'")["role"] == "admin")
        run("UPDATE users SET role = 'user' WHERE email = 'plain@example.com'")

        # ================= Access control =================
        anon, user, admin = app.test_client(), app.test_client(), app.test_client()
        user.post("/login", data={"email": "demo@example.com", "password": "Demo@1234"})
        admin.post("/login", data={"email": "admin@example.com", "password": "Admin@1234"})

        pages = ["/admin", "/admin/users", "/admin/jobs", "/admin/jobs/new", "/admin/exams", "/admin/exams/new",
                 "/admin/subjects", "/admin/materials", "/admin/materials/new", "/admin/papers",
                 "/admin/resources", "/admin/mock-tests", "/admin/questions", "/admin/questions/new",
                 "/admin/results"]
        r = anon.get("/admin")
        check("Anonymous visitor is redirected to login", r.status_code == 302 and "/login" in r.headers["Location"])
        check("Normal user gets 403 on every admin page", all(user.get(p).status_code == 403 for p in pages))
        check("Admin can open every admin page", all(admin.get(p).status_code == 200 for p in pages))

        job_id = one("SELECT id FROM jobs WHERE title LIKE '%Auditor%'")["id"]
        r = user.post(f"/admin/jobs/{job_id}/delete")
        check("Normal user cannot delete a job", r.status_code == 403 and one("SELECT id FROM jobs WHERE id = ?", (job_id,)))
        r = anon.post(f"/admin/jobs/{job_id}/delete")
        check("Anonymous POST goes to login without a 'next' link", r.status_code == 302 and "next=" not in r.headers["Location"])
        check("Navbar shows the Admin Panel link to admins only",
              "Admin Panel" in admin.get("/").get_data(as_text=True) and "Admin Panel" not in user.get("/").get_data(as_text=True))

        # ================= Overview =================
        html = flat(admin.get("/admin"))
        for text in ["Registered users", "Open jobs", "Practice questions", "Mock tests", "Recent registrations",
                     "Recent mock test attempts", "Mock test usage", "have not been verified yet"]:
            check(f"Overview shows '{text}'", text in html)

        # ================= Users =================
        html = flat(admin.get("/admin/users"))
        check("Users page lists users without password hashes",
              "demo@example.com" in html and "scrypt:" not in html and "pbkdf2:" not in html)
        check("Users search works", "Demo Student" in flat(admin.get("/admin/users?q=demo")) and "Admin User" not in flat(admin.get("/admin/users?q=demo")))
        check("Users search treats % literally", "No users found" in flat(admin.get("/admin/users?q=%25")))
        demo = one("SELECT id FROM users WHERE email = 'demo@example.com'")
        admin.post(f"/admin/users/{demo['id']}/role", data={"role": "admin"})
        check("Admin can promote a user", one("SELECT role FROM users WHERE id = ?", (demo["id"],))["role"] == "admin")
        check("Role change applies immediately", user.get("/admin").status_code == 200)
        admin.post(f"/admin/users/{demo['id']}/role", data={"role": "user"})
        check("Admin can demote a user", one("SELECT role FROM users WHERE id = ?", (demo["id"],))["role"] == "user")
        check("Demoted user is locked out again", user.get("/admin").status_code == 403)
        admin.post(f"/admin/users/{demo['id']}/role", data={"role": "root"})
        check("Invalid role is rejected", one("SELECT role FROM users WHERE id = ?", (demo["id"],))["role"] == "user")
        admin.post(f"/admin/users/{admin_row['id']}/role", data={"role": "user"})
        check("Admin cannot demote themselves", one("SELECT role FROM users WHERE id = ?", (admin_row["id"],))["role"] == "admin")
        admin.post(f"/admin/users/{admin_row['id']}/delete")
        check("Admin cannot delete themselves", one("SELECT id FROM users WHERE id = ?", (admin_row["id"],)) is not None)

        with standalone_db(db_path) as conn:
            temp_id = create_user("Temp User", "temp@example.com", generate_password_hash("Temp@1234"),
                                  "2000-01-01", "Graduate (Bachelor's Degree)", "Andhra Pradesh", "Guntur", conn=conn)
        test_id = one("SELECT id FROM mock_tests LIMIT 1")["id"]
        run("""INSERT INTO test_attempts (user_id, mock_test_id, started_at, submitted_at, total_questions,
               correct_count, score_percent, time_taken_seconds, status)
               VALUES (?, ?, '2026-01-01 10:00:00', '2026-01-01 10:05:00', 10, 8, 80.0, 300, 'submitted')""",
            (temp_id, test_id))
        run("INSERT INTO saved_jobs (user_id, job_id) VALUES (?, ?)", (temp_id, job_id))
        html = flat(admin.get("/admin/results"))
        check("Results page shows the attempt with the student's name", "Temp User" in html and "80%" in html)
        check("Results filter by exam works",
              "Temp User" in flat(admin.get(f"/admin/results?exam={one('SELECT exam_id FROM mock_tests WHERE id = ?', (test_id,))['exam_id']}")))
        check("Results search by name", "No submitted attempts" in flat(admin.get("/admin/results?q=zzz")))
        admin.post(f"/admin/users/{temp_id}/delete")
        check("Deleting a user removes them and their data",
              one("SELECT id FROM users WHERE id = ?", (temp_id,)) is None
              and not sql("SELECT id FROM test_attempts WHERE user_id = ?", (temp_id,))
              and not sql("SELECT id FROM saved_jobs WHERE user_id = ?", (temp_id,)))
        check("Deleting an unknown user gives 404", admin.post("/admin/users/99999/delete").status_code == 404)

        # ================= Jobs =================
        ssc = one("SELECT id FROM exams WHERE short_code = 'SSC-CGL'")["id"]
        chsl = one("SELECT id FROM exams WHERE short_code = 'SSC-CHSL'")["id"]
        job_form = {
            "title": "Test Clerk Post", "organization": "Test Org", "govt_category": "Central", "exam_category": "SSC",
            "min_qualification_level": "2", "required_qualification": "12th pass", "min_age": "18", "max_age": "27",
            "state_requirement": "", "vacancies": "50", "vacancies_note": "", "application_start": "2026-01-01",
            "application_deadline": "2099-12-31", "salary": "Sample pay", "description": "Description text",
            "eligibility_text": "Eligibility text", "syllabus_pattern": "Pattern text",
            "notification_url": "https://ssc.gov.in/", "apply_url": "https://ssc.gov.in/", "is_demo": "1",
            "exam_ids": [str(ssc), str(chsl)]}
        jobs_before = one("SELECT COUNT(*) AS c FROM jobs")["c"]
        r = admin.post("/admin/jobs/new", data=job_form)
        check("Valid job is created", r.status_code == 302 and one("SELECT COUNT(*) AS c FROM jobs")["c"] == jobs_before + 1)
        job = one("SELECT * FROM jobs WHERE title = 'Test Clerk Post'")
        check("Job fields are saved correctly", job["min_age"] == 18 and job["max_age"] == 27 and job["vacancies"] == 50
              and job["application_deadline"] == "2099-12-31" and job["is_demo"] == 1)
        check("Demo vacancies get a 'sample figure' note", "Sample figure" in (job["vacancies_note"] or ""))
        check("Job is linked to both exams (job_exams)", len(sql("SELECT * FROM job_exams WHERE job_id = ?", (job["id"],))) == 2)
        check("New job is visible on the public jobs page", "Test Clerk Post" in flat(app.test_client().get("/jobs?q=Test+Clerk")))

        bad_cases = [
            ("Missing title", {"title": ""}, "Job title is required"),
            ("Minimum age above maximum", {"min_age": "40", "max_age": "30"}, "Minimum age cannot be greater"),
            ("javascript: link", {"apply_url": "javascript:alert(1)"}, "full http"),
            ("Impossible date", {"application_deadline": "2026-13-45"}, "valid date"),
            ("Deadline before start", {"application_start": "2030-01-01", "application_deadline": "2029-01-01"}, "cannot be before"),
            ("Invalid government category", {"govt_category": "Mars"}, "valid government category"),
            ("Qualification level out of range", {"min_qualification_level": "9"}, "between 1 and 5"),
            ("Age below 14", {"min_age": "5"}, "between 14 and 70"),
        ]
        for label, change, message in bad_cases:
            r = admin.post("/admin/jobs/new", data={**job_form, "title": "Bad Job", **change})
            check(f"Job form rejects: {label}", r.status_code == 200 and message in flat(r))
        check("No invalid job was saved", one("SELECT COUNT(*) AS c FROM jobs")["c"] == jobs_before + 1)
        check("Entered values are kept after an error", "Test Org" in admin.post("/admin/jobs/new", data={**job_form, "title": ""}).get_data(as_text=True))

        r = admin.post(f"/admin/jobs/{job['id']}/edit", data={**job_form, "title": "Test Clerk Post v2", "salary": "New pay", "exam_ids": [str(chsl)]})
        check("Job can be edited", r.status_code == 302 and one("SELECT salary FROM jobs WHERE id = ?", (job["id"],))["salary"] == "New pay")
        check("Editing replaces the exam links", [x["exam_id"] for x in sql("SELECT exam_id FROM job_exams WHERE job_id = ?", (job["id"],))] == [chsl])
        check("Edit form is pre-filled", "Test Clerk Post v2" in admin.get(f"/admin/jobs/{job['id']}/edit").get_data(as_text=True))
        check("Editing an unknown job gives 404", admin.get("/admin/jobs/99999/edit").status_code == 404)

        evil = "x'); DROP TABLE jobs;--"
        admin.post("/admin/jobs/new", data={**job_form, "title": evil})
        check("SQL-injection text is stored as plain text", one("SELECT id FROM jobs WHERE title = ?", (evil,)) is not None
              and one("SELECT COUNT(*) AS c FROM jobs")["c"] == jobs_before + 2)
        check("Admin job list search works", "Test Clerk Post v2" in flat(admin.get("/admin/jobs?q=clerk+post")))

        run("INSERT INTO saved_jobs (user_id, job_id) VALUES (?, ?)", (demo["id"], job["id"]))
        r = admin.post(f"/admin/jobs/{job['id']}/delete")
        check("Job can be deleted", r.status_code == 302 and one("SELECT id FROM jobs WHERE id = ?", (job["id"],)) is None)
        check("Deleting a job removes its exam links and bookmarks",
              not sql("SELECT * FROM job_exams WHERE job_id = ?", (job["id"],)) and not sql("SELECT * FROM saved_jobs WHERE job_id = ?", (job["id"],)))

        # ================= Exams =================
        exam_form = {"name": "Test Exam Alpha", "short_code": "tea-1", "category": "Other", "conducting_body": "Test Body",
                     "govt_level": "Central", "description": "d", "exam_pattern": "p", "syllabus_summary": "s",
                     "official_url": "https://example.org/"}
        r = admin.post("/admin/exams/new", data=exam_form)
        exam = one("SELECT * FROM exams WHERE name = 'Test Exam Alpha'")
        check("Exam is created and the code is upper-cased", r.status_code == 302 and exam["short_code"] == "TEA-1")
        check("Duplicate exam is rejected", "already used by another exam" in flat(admin.post("/admin/exams/new", data=exam_form)))
        check("Invalid exam category is rejected", "valid category" in flat(admin.post("/admin/exams/new", data={**exam_form, "name": "Other", "short_code": "X1", "category": "Bogus"})))
        check("Bad short code is rejected", "letters, numbers and hyphens" in flat(admin.post("/admin/exams/new", data={**exam_form, "name": "Other2", "short_code": "A B!"})))
        admin.post(f"/admin/exams/{exam['id']}/edit", data={**exam_form, "description": "Changed"})
        check("Exam can be edited", one("SELECT description FROM exams WHERE id = ?", (exam["id"],))["description"] == "Changed")
        check("Edited exam shows on the public exams page", "Test Exam Alpha" in flat(app.test_client().get("/exams")))

        # ================= Subjects =================
        r = admin.post("/admin/subjects/save", data={"exam_id": exam["id"], "name": "Test Subject", "description": "ds"})
        subject = one("SELECT * FROM subjects WHERE name = 'Test Subject'")
        check("Subject is created", r.status_code == 302 and subject is not None and subject["exam_id"] == exam["id"])
        check("Duplicate subject in the same exam is rejected",
              "already has a subject" in flat(admin.post("/admin/subjects/save", data={"exam_id": exam["id"], "name": "Test Subject"}, follow_redirects=True)))
        admin.post("/admin/subjects/save", data={"id": subject["id"], "exam_id": ssc, "name": "Test Subject Renamed"})
        changed = one("SELECT * FROM subjects WHERE id = ?", (subject["id"],))
        check("Subject can be renamed", changed["name"] == "Test Subject Renamed")
        check("The exam of a subject cannot be changed", changed["exam_id"] == exam["id"])
        check("Subject edit mode loads", "Edit subject" in flat(admin.get(f"/admin/subjects?edit={subject['id']}")))
        check("Subject with an invalid exam is rejected", "valid exam" in flat(admin.post("/admin/subjects/save", data={"exam_id": "99999", "name": "Ghost"}, follow_redirects=True)))
        sid = subject["id"]

        # ================= Study materials and PDF uploads =================
        base = {"subject_id": sid, "title": "Test Link", "description": "", "resource_type": "Link", "url": "https://example.org/x"}
        r = admin.post("/admin/materials/new", data=base)
        link = one("SELECT * FROM study_materials WHERE title = 'Test Link'")
        check("Link material is created", r.status_code == 302 and link["url"] == "https://example.org/x" and link["is_official"] == 0)
        check("Link material appears publicly", "Test Link" in flat(app.test_client().get(f"/materials?subject={sid}")))

        r = admin.post("/admin/materials/new", data={**base, "title": "Test PDF", "resource_type": "PDF", "url": "", "file": pdf(name="My Notes.pdf")},
                       content_type="multipart/form-data")
        doc = one("SELECT * FROM study_materials WHERE title = 'Test PDF'")
        check("PDF material is created", r.status_code == 302 and doc and doc["file_path"].endswith("My_Notes.pdf"))
        check("The PDF is stored in the uploads folder under a safe name", doc and doc["file_path"] in files())
        r = app.test_client().get(f"/materials/{doc['id']}/file")
        check("Uploaded PDF can be opened by students", r.status_code == 200 and r.data.startswith(b"%PDF-"))

        before = files()
        r = admin.post("/admin/materials/new", data={**base, "title": "Fake PDF", "url": "", "file": pdf(b"MZ this is not a pdf", "evil.pdf")}, content_type="multipart/form-data")
        check("A fake PDF (wrong content) is rejected", r.status_code == 200 and "not a valid PDF" in flat(r))
        r = admin.post("/admin/materials/new", data={**base, "title": "Exe File", "url": "", "file": pdf(name="run.exe")}, content_type="multipart/form-data")
        check("A non-PDF extension is rejected", "Only PDF files are allowed" in flat(r))
        r = admin.post("/admin/materials/new", data={**base, "title": "Traversal", "url": "", "file": pdf(name="../../evil.pdf")}, content_type="multipart/form-data")
        check("A path-traversal file name stays inside the uploads folder",
              r.status_code == 302 and not os.path.exists(os.path.join(tmp, "evil.pdf"))
              and len(files()) == len(before) + 1)
        check("Rejected uploads left no files and no records", one("SELECT id FROM study_materials WHERE title IN ('Fake PDF', 'Exe File')") is None)
        trav = one("SELECT * FROM study_materials WHERE title = 'Traversal'")
        admin.post(f"/admin/materials/{trav['id']}/delete")

        check("Material without a link or a file is rejected", "external link or upload a PDF" in flat(admin.post("/admin/materials/new", data={**base, "title": "Empty", "url": ""})))
        check("Material with a non-http link is rejected", "full http" in flat(admin.post("/admin/materials/new", data={**base, "title": "Bad URL", "url": "ftp://x.com/f"})))
        check("Material with an unknown subject is rejected", "valid subject" in flat(admin.post("/admin/materials/new", data={**base, "subject_id": "99999"})))

        old_name = doc["file_path"]
        r = admin.post(f"/admin/materials/{doc['id']}/edit", data={**base, "title": "Test PDF", "resource_type": "PDF", "url": "", "file": pdf(name="second.pdf")}, content_type="multipart/form-data")
        doc2 = one("SELECT * FROM study_materials WHERE id = ?", (doc["id"],))
        check("Replacing a PDF stores the new file", r.status_code == 302 and doc2["file_path"].endswith("second.pdf") and doc2["file_path"] in files())
        check("Replacing a PDF deletes the old file", old_name not in files())
        r = admin.post(f"/admin/materials/{doc['id']}/edit", data={**base, "title": "Test PDF", "resource_type": "PDF", "url": "", "remove_file": "1"})
        check("The only resource cannot be removed", "no external link" in flat(r) and one("SELECT file_path FROM study_materials WHERE id = ?", (doc["id"],))["file_path"])
        r = admin.post(f"/admin/materials/{doc['id']}/edit", data={**base, "title": "Test PDF", "resource_type": "PDF", "url": "https://example.org/pdf", "remove_file": "1"})
        check("A PDF can be removed when a link exists", one("SELECT file_path FROM study_materials WHERE id = ?", (doc["id"],))["file_path"] is None and doc2["file_path"] not in files())
        admin.post("/admin/materials/new", data={**base, "title": "Delete Me PDF", "url": "", "file": pdf(name="gone.pdf")}, content_type="multipart/form-data")
        gone = one("SELECT * FROM study_materials WHERE title = 'Delete Me PDF'")
        admin.post(f"/admin/materials/{gone['id']}/delete")
        check("Deleting a material deletes its file", gone["file_path"] not in files() and one("SELECT id FROM study_materials WHERE id = ?", (gone["id"],)) is None)
        check("Admin materials search works", "Test Link" in flat(admin.get("/admin/materials?q=Test+Link")))

        # ================= Previous papers =================
        paper = {"exam_id": exam["id"], "title": "Test Paper 2019", "year": "2019", "url": "https://example.org/p", "is_official": "1"}
        r = admin.post("/admin/papers/save", data=paper)
        row = one("SELECT * FROM previous_papers WHERE title = 'Test Paper 2019'")
        check("Previous paper is created", r.status_code == 302 and row["year"] == 2019 and row["is_official"] == 1)
        check("Previous paper appears publicly", "Test Paper 2019" in flat(app.test_client().get(f"/previous-papers?exam={exam['id']}")))
        check("Impossible year is rejected", "between 1990 and 2100" in flat(admin.post("/admin/papers/save", data={**paper, "title": "Old", "year": "1800"}, follow_redirects=True)))
        admin.post("/admin/papers/save", data={**paper, "title": "Paper PDF", "url": "", "file": pdf(name="p.pdf")}, content_type="multipart/form-data")
        pp = one("SELECT * FROM previous_papers WHERE title = 'Paper PDF'")
        check("Paper PDF is uploaded and can be opened", pp and pp["file_path"] in files() and app.test_client().get(f"/previous-papers/{pp['id']}/file").status_code == 200)
        admin.post("/admin/papers/save", data={"id": row["id"], **paper, "title": "Test Paper 2019 (edited)"})
        check("Previous paper can be edited", one("SELECT title FROM previous_papers WHERE id = ?", (row["id"],))["title"] == "Test Paper 2019 (edited)")
        admin.post(f"/admin/papers/{pp['id']}/delete")
        check("Deleting a paper deletes its PDF", pp["file_path"] not in files() and one("SELECT id FROM previous_papers WHERE id = ?", (pp["id"],)) is None)

        # ================= Official links =================
        res_form = {"title": "Test Official Link", "url": "https://example.org/official", "description": "d",
                    "resource_kind": "Portal", "exam_id": "", "last_verified": ""}
        admin.post("/admin/resources/save", data=res_form)
        res = one("SELECT * FROM official_resources WHERE title = 'Test Official Link'")
        check("Official link is created as 'not verified'", res is not None and res["last_verified"] is None)
        check("Non-http link is rejected", "full http" in flat(admin.post("/admin/resources/save", data={**res_form, "title": "FTP", "url": "ftp://x.org"}, follow_redirects=True)))
        check("Missing link is rejected", "Link is required" in flat(admin.post("/admin/resources/save", data={**res_form, "title": "No URL", "url": ""}, follow_redirects=True)))
        admin.post(f"/admin/resources/{res['id']}/verify")
        from datetime import date
        check("'Mark verified today' stores today's date", one("SELECT last_verified FROM official_resources WHERE id = ?", (res["id"],))["last_verified"] == date.today().isoformat())
        admin.post("/admin/resources/save", data={"id": res["id"], **res_form, "url": "https://example.org/changed"})
        check("Changing a link resets it to 'not verified'", one("SELECT last_verified FROM official_resources WHERE id = ?", (res["id"],))["last_verified"] is None)
        check("A changed link appears on the public preparation page without code changes", "https://example.org/changed" in flat(app.test_client().get("/preparation")))
        admin.post(f"/admin/resources/{res['id']}/delete")
        check("Official link can be deleted", one("SELECT id FROM official_resources WHERE id = ?", (res["id"],)) is None)

        # ================= Questions =================
        q_form = {"subject_id": sid, "question_text": "What is 2 + 2?", "option_a": "3", "option_b": "4", "option_c": "5",
                  "option_d": "6", "correct_option": "B", "explanation": "Basic addition.", "difficulty": "Easy", "is_demo": "1"}
        r = admin.post("/admin/questions/new", data=q_form)
        q1 = one("SELECT * FROM questions WHERE question_text = 'What is 2 + 2?'")
        check("Question is created", r.status_code == 302 and q1["correct_option"] == "B" and q1["is_demo"] == 1)
        check("Duplicate options are rejected", "must all be different" in flat(admin.post("/admin/questions/new", data={**q_form, "question_text": "Dup", "option_b": "3"})))
        check("Invalid correct answer is rejected", "valid correct answer" in flat(admin.post("/admin/questions/new", data={**q_form, "question_text": "Bad", "correct_option": "E"})))
        check("Missing option is rejected", "Option C is required" in flat(admin.post("/admin/questions/new", data={**q_form, "question_text": "Bad2", "option_c": ""})))
        check("Invalid subject is rejected", "valid subject" in flat(admin.post("/admin/questions/new", data={**q_form, "question_text": "Bad3", "subject_id": "99999"})))
        check("No invalid question was saved", one("SELECT COUNT(*) AS c FROM questions WHERE subject_id = ?", (sid,))["c"] == 1)
        admin.post(f"/admin/questions/{q1['id']}/edit", data={**q_form, "correct_option": "C"})
        check("Question can be edited", one("SELECT correct_option FROM questions WHERE id = ?", (q1["id"],))["correct_option"] == "C")
        admin.post("/admin/questions/new", data={**q_form, "question_text": "What is 3 + 3?", "option_a": "5", "option_b": "6", "option_c": "7", "option_d": "8"})
        admin.post("/admin/questions/new", data={**q_form, "question_text": "What is 4 + 4?", "option_a": "7", "option_b": "8", "option_c": "9", "option_d": "10"})
        check("Admin questions list search works", "What is 3 + 3?" in flat(admin.get("/admin/questions?q=3+%2B+3")))
        check("New question is visible to students", "What is 2 + 2?" in flat(app.test_client().get(f"/practice-questions?subject={sid}")))

        # ================= Mock tests =================
        t_form = {"title": "", "subject_id": sid, "duration_minutes": "5", "num_questions": "2", "is_active": "1"}
        admin.post("/admin/mock-tests/save", data=t_form)
        test = one("SELECT * FROM mock_tests WHERE subject_id = ?", (sid,))
        check("Mock test is created with a generated title", test is not None and "TEA-1" in test["title"] and test["exam_id"] == exam["id"])
        check("A second test for the same subject is rejected", "already has a mock test" in flat(admin.post("/admin/mock-tests/save", data=t_form, follow_redirects=True)))
        check("Zero duration is rejected", "between 1 and 180" in flat(admin.post("/admin/mock-tests/save", data={**t_form, "duration_minutes": "0"}, follow_redirects=True)))
        admin.post("/admin/mock-tests/save", data={"id": test["id"], **t_form, "title": "My Custom Test", "duration_minutes": "7"})
        check("Mock test can be edited", one("SELECT title, duration_minutes FROM mock_tests WHERE id = ?", (test["id"],))["duration_minutes"] == 7)
        student = app.test_client()
        student.post("/login", data={"email": "demo@example.com", "password": "Demo@1234"})
        check("Admin-created test is listed for students", "My Custom Test" in flat(student.get("/mock-tests")))
        r = student.post(f"/mock-tests/{test['id']}/start")
        attempt_id = int(r.headers["Location"].split("/attempts/")[1].split("/")[0])
        check("A student can start the admin-created test with 2 questions",
              one("SELECT COUNT(*) AS c FROM user_answers WHERE attempt_id = ?", (attempt_id,))["c"] == 2)
        admin.post("/admin/mock-tests/save", data={"id": test["id"], **t_form, "title": "My Custom Test", "is_active": ""})
        check("A hidden test disappears from the student list", "My Custom Test" not in flat(student.get("/mock-tests")))

        # ================= Cascade delete =================
        admin.post("/admin/materials/new", data={**base, "title": "Cascade PDF", "url": "", "file": pdf(name="cascade.pdf")}, content_type="multipart/form-data")
        admin.post("/admin/papers/save", data={**paper, "title": "Cascade Paper", "url": "", "file": pdf(name="cascade2.pdf")}, content_type="multipart/form-data")
        casc = [one("SELECT file_path FROM study_materials WHERE title = 'Cascade PDF'")["file_path"],
                one("SELECT file_path FROM previous_papers WHERE title = 'Cascade Paper'")["file_path"]]
        check("Cascade test files exist before deleting", all(name in files() for name in casc))
        r = admin.post(f"/admin/exams/{exam['id']}/delete")
        check("Exam can be deleted", r.status_code == 302 and one("SELECT id FROM exams WHERE id = ?", (exam["id"],)) is None)
        check("Deleting an exam removes subjects, questions, tests, papers and attempts",
              not sql("SELECT id FROM subjects WHERE exam_id = ?", (exam["id"],))
              and not sql("SELECT id FROM questions WHERE subject_id = ?", (sid,))
              and not sql("SELECT id FROM mock_tests WHERE exam_id = ?", (exam["id"],))
              and not sql("SELECT id FROM previous_papers WHERE exam_id = ?", (exam["id"],))
              and not sql("SELECT id FROM test_attempts WHERE id = ?", (attempt_id,)))
        check("Deleting an exam also deletes the uploaded files under it", all(name not in files() for name in casc))
        check("Foreign key check finds no problems", not sql("PRAGMA foreign_key_check"))
        check("Deleting an unknown exam gives 404", admin.post("/admin/exams/99999/delete").status_code == 404)

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()