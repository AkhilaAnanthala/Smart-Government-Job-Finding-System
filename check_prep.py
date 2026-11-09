"""check_prep.py - tests the Preparation Hub pages, filters and safe PDF serving."""
import os
import tempfile

import seed_data
from app import create_app
from db import standalone_db, query_db, execute_db

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def flat(response):
    """Page HTML with all runs of whitespace collapsed to one space."""
    return " ".join(response.get_data(as_text=True).split())


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        upload = os.path.join(tmp, "uploads")
        app = create_app({"DATABASE_PATH": db_path, "UPLOAD_FOLDER": upload,
                          "WTF_CSRF_ENABLED": False, "TESTING": True})

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)

            ssc = seed_data.exam_id_for("SSC-CGL", conn)
            upsc = seed_data.exam_id_for("UPSC-CSE", conn)
            appsc2 = seed_data.exam_id_for("APPSC-G2", conn)
            rrb = seed_data.exam_id_for("RRB-NTPC", conn)
            ssc_ga = seed_data.subject_id_for("SSC-CGL", "General Awareness", conn)
            auditor = query_db("SELECT id FROM jobs WHERE title LIKE '%Auditor%'", one=True, conn=conn)

            # Extra test records: two uploaded PDFs, one path-traversal attempt
            with open(os.path.join(upload, "abc123_test.pdf"), "wb") as f:
                f.write(b"%PDF-1.4\n%test file\n")
            with open(os.path.join(upload, "paper1_test.pdf"), "wb") as f:
                f.write(b"%PDF-1.4\n%test paper\n")
            with open(os.path.join(tmp, "secret.txt"), "w") as f:
                f.write("top secret")

            pdf_id = execute_db(
                """INSERT INTO study_materials (subject_id, title, description, resource_type, file_path, is_official)
                   VALUES (?, 'Test Notes PDF', 'uploaded test file', 'PDF', 'abc123_test.pdf', 0)""",
                (ssc_ga,), conn=conn)
            evil_id = execute_db(
                """INSERT INTO study_materials (subject_id, title, resource_type, file_path, is_official)
                   VALUES (?, 'Traversal Test', 'PDF', '../secret.txt', 0)""", (ssc_ga,), conn=conn)
            link_id = query_db("SELECT id FROM study_materials WHERE title LIKE 'NCERT%'", one=True, conn=conn)["id"]
            paper_id = execute_db(
                """INSERT INTO previous_papers (exam_id, title, year, file_path, is_official)
                   VALUES (?, 'Uploaded Paper 2020', 2020, 'paper1_test.pdf', 0)""", (ssc,), conn=conn)

        client = app.test_client()

        # ================= Hub and exam pages =================
        r = client.get("/preparation")
        html = flat(r)
        check("Preparation hub loads", r.status_code == 200 and "Preparation Hub" in html)
        check("Hub shows the Job > Exam > Subject chain", "Government Job" in html and "Recruitment Exam" in html)
        check("Hub lists exams by category", "SSC Combined Graduate Level" in html and "RRB Group D" in html)
        check("Mock-test resource says the portal does not host it", "does not host" in html)

        html = flat(client.get("/exams"))
        check("Exam list shows every exam", "RRB Group D" in html and "AP Teacher Recruitment Test (DSC)" in html)
        html = flat(client.get("/exams?category=SSC"))
        check("Exam filter: category", "SSC Combined Graduate Level" in html and "RRB Group D" not in html)
        html = flat(client.get("/exams?govt=Andhra+Pradesh"))
        check("Exam filter: Andhra Pradesh", "APPSC Group-I Services" in html and "SSC Combined Graduate Level" not in html)
        html = flat(client.get("/exams?q=railway"))
        check("Exam search matches the conducting body", "RRB Non-Technical" in html and "SSC Combined Graduate Level" not in html)
        check("A % in exam search is literal", "No examinations match" in flat(client.get("/exams?q=%25")))
        check("SQL-injection style text is harmless", client.get("/exams?q=%27+OR+1%3D1+--&category=x").status_code == 200)

        r = client.get(f"/exams/{ssc}")
        html = flat(r)
        check("Exam details load", r.status_code == 200 and "SSC Combined Graduate Level" in html)
        check("Exam shows jobs that share it", "Auditor" in html and "Inspector (Taxation)" in html and "Station Master" not in html)
        check("Exam shows its subjects", "Quantitative Aptitude" in html and "General Intelligence" in html)
        check("Exam shows official resource matched by website", "SSC Syllabus" in html)
        check("Exam shows its mock tests", "Quantitative Aptitude" in html and "minutes" in html)
        check("Exam shows an uploaded paper", "Uploaded Paper 2020" in html)
        check("UPSC page shows its official papers resource", "UPSC Previous Question Papers" in flat(client.get(f"/exams/{upsc}")))
        check("Exam without a stored link says so", "No official website link has been configured" in flat(client.get(f"/exams/{rrb}")))
        check("Unknown exam gives 404", client.get("/exams/99999").status_code == 404)

        r = client.get(f"/exams/{ssc}/syllabus")
        html = flat(r)
        check("Syllabus page loads", r.status_code == 200 and "Syllabus summary" in html)
        check("Syllabus shows pattern and summary", "Computer-based tiers" in html and "quantitative aptitude, English language" in html)
        check("Syllabus advises checking the official notification", "official notification" in html)
        check("Syllabus links to official page", "SSC Syllabus" in html)
        check("Unknown syllabus gives 404", client.get("/exams/99999/syllabus").status_code == 404)
        check("Job details now link to exam details",
              f"/exams/{ssc}" in client.get(f"/jobs/{auditor['id']}").get_data(as_text=True))

        # ================= Study materials =================
        r = client.get("/materials")
        html = flat(r)
        check("Materials page loads", r.status_code == 200 and "NCERT Textbooks (free, official)" in html)
        check("Official and additional badges are shown", "Official" in html and "Additional resource" in html)
        check("External links open safely in a new tab", 'rel="noopener noreferrer"' in html)
        check("Uploaded PDF has a Download button", "Test Notes PDF" in html and "Download" in html)
        html = flat(client.get(f"/materials?exam={upsc}"))
        check("Materials filter: exam", "India Code" in html and "SSC Syllabus (official)" not in html)
        html = flat(client.get(f"/materials?subject={ssc_ga}"))
        check("Materials filter: subject", "SSC Syllabus (official)" in html and "India Code" not in html)
        html = flat(client.get("/materials?source=additional"))
        check("Materials filter: additional only", "Test Notes PDF" in html and "India Code" not in html)
        html = flat(client.get("/materials?source=official"))
        check("Materials filter: official only", "India Code" in html and "Test Notes PDF" not in html)
        check("Materials filter: type PDF", "Test Notes PDF" in flat(client.get("/materials?type=PDF")))
        check("Materials filter: type with no match", "No study materials match" in flat(client.get("/materials?type=Video")))
        html = flat(client.get("/materials?q=constitution"))
        check("Materials search", "India Code" in html and "Test Notes PDF" not in html)
        check("A % in materials search is literal", "No study materials match" in flat(client.get("/materials?q=%25")))
        check("Invalid material filters are ignored",
              client.get("/materials?exam=abc&subject=99999&type=x&source=y&page=zzz").status_code == 200)

        # ================= Safe PDF serving =================
        r = client.get(f"/materials/{pdf_id}/file")
        check("Uploaded PDF opens inline",
              r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF-"))
        r = client.get(f"/materials/{pdf_id}/file?download=1")
        check("Download forces an attachment", r.status_code == 200 and "attachment" in r.headers.get("Content-Disposition", ""))
        check("Path traversal file name is blocked", client.get(f"/materials/{evil_id}/file").status_code == 404)
        check("Link-only material has no file", client.get(f"/materials/{link_id}/file").status_code == 404)
        check("Unknown material gives 404", client.get("/materials/99999/file").status_code == 404)
        r = client.get(f"/previous-papers/{paper_id}/file")
        check("Uploaded paper opens", r.status_code == 200 and r.data.startswith(b"%PDF-"))
        check("Unknown paper gives 404", client.get("/previous-papers/99999/file").status_code == 404)

        # ================= Previous papers =================
        html = flat(client.get("/previous-papers"))
        check("Previous papers page loads", "UPSC previous question papers" in html and "Uploaded Paper 2020" in html)
        check("Previous papers show official source box", "UPSC Previous Question Papers" in html)
        html = flat(client.get(f"/previous-papers?exam={appsc2}"))
        check("Papers filter: exam", "APPSC syllabus and old question papers" in html and "UPSC previous question papers" not in html)
        html = flat(client.get("/previous-papers?year=2020"))
        check("Papers filter: year", "Uploaded Paper 2020" in html and "UPSC previous question papers" not in html)
        check("Papers filter: year with no match", "No previous papers match" in flat(client.get("/previous-papers?year=1999")))
        html = flat(client.get("/previous-papers?source=additional"))
        check("Papers filter: additional only", "Uploaded Paper 2020" in html and "UPSC previous question papers" not in html)
        check("Invalid paper filters are ignored", client.get("/previous-papers?year=abc&exam=x&source=z").status_code == 200)

        # ================= Practice questions =================
        r = client.get("/practice-questions")
        html = flat(r)
        check("Practice questions load", r.status_code == 200 and "80 questions found" in html)
        check("Demo disclaimer is shown", "created for demonstration purposes" in html)
        check("Answers are behind a toggle", "Show answer and explanation" in html)
        page1 = flat(client.get("/practice-questions"))
        page2 = flat(client.get("/practice-questions?page=2"))
        check("Pagination: page 2 differs from page 1", "Dakshina Ganga" in page1 and "Dakshina Ganga" not in page2)
        check("Page beyond the end is handled", client.get("/practice-questions?page=999").status_code == 200)
        html = flat(client.get(f"/practice-questions?subject={ssc_ga}"))
        check("Questions filter: subject", "first President of India" in html and "What is 15% of 200" not in html)
        check("Question shows its correct answer text", "Rajendra Prasad" in html)
        html = flat(client.get("/practice-questions?difficulty=Hard"))
        check("Questions filter: difficulty", "Kolleru Lake" in html and "Sorrow of Bihar" not in html)
        html = flat(client.get(f"/practice-questions?exam={upsc}"))
        check("Questions filter: exam", "Directive Principles" in html and "Dakshina Ganga" not in html)
        check("Invalid question filters are ignored",
              client.get("/practice-questions?exam=abc&subject=-1&difficulty=Extreme&page=0").status_code == 200)

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()