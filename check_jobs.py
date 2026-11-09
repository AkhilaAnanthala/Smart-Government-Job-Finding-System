"""check_jobs.py - tests job search, filters, details, eligibility rules and bookmarks."""
import os
import tempfile

import seed_data
from app import create_app
from db import standalone_db, query_db
from eligibility import check_job_eligibility

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def job_by_title(conn, fragment):
    return query_db("SELECT * FROM jobs WHERE title LIKE ?", (f"%{fragment}%",), one=True, conn=conn)


def result_for(job, age, level, state):
    return check_job_eligibility(job, age, level, state)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        app = create_app({"DATABASE_PATH": db_path, "WTF_CSRF_ENABLED": False, "TESTING": True})

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)
            seed_data.seed_demo_user(conn)
            auditor = job_by_title(conn, "Auditor")
            station = job_by_title(conn, "Station Master")
            sgt = job_by_title(conn, "Secondary Grade Teacher")
            ldc = job_by_title(conn, "Lower Division Clerk")
            mts = job_by_title(conn, "Multi Tasking Staff")
            track = job_by_title(conn, "Track Maintainer")
            group2 = job_by_title(conn, "Group-II Executive")
            stat_inv = job_by_title(conn, "Statistical Investigator")
            ssc_cgl = query_db("SELECT id FROM exams WHERE short_code = 'SSC-CGL'", one=True, conn=conn)
            demo_user = query_db("SELECT id FROM users WHERE email = 'demo@example.com'", one=True, conn=conn)

        # ================= Eligibility engine (pure Python) =================
        r = result_for(auditor, 25, 4, "Andhra Pradesh")
        check("Graduate aged 25 is eligible for Auditor", r["status"] == "eligible")
        r = result_for(auditor, 25, 1, "Andhra Pradesh")
        check("10th pass is not eligible for Auditor, with a reason",
              r["status"] == "not_eligible" and any("not satisfied" in x["text"] for x in r["reasons"]))
        r = result_for(auditor, 30, 4, "Andhra Pradesh")
        check("Over the age limit gives 'verify', not 'eligible'",
              r["status"] == "verify" and any("relaxation" in x["text"] for x in r["reasons"]))
        check("Below the minimum age is not eligible", result_for(auditor, 17, 4, "Andhra Pradesh")["status"] == "not_eligible")
        check("Teacher post with specific training needs verification",
              result_for(sgt, 25, 3, "Andhra Pradesh")["status"] == "verify")
        check("12th pass is not eligible for the teacher post", result_for(sgt, 25, 2, "Andhra Pradesh")["status"] == "not_eligible")
        check("State requirement mismatch is not eligible", result_for(sgt, 25, 3, "Telangana")["status"] == "not_eligible")
        check("ITI/Diploma vs 12th-pass post needs verification", result_for(ldc, 25, 3, "Andhra Pradesh")["status"] == "verify")
        check("12th pass is not eligible for a graduate post", result_for(station, 25, 2, "Andhra Pradesh")["status"] == "not_eligible")
        check("Graduate aged 22 is eligible for MTS", result_for(mts, 22, 4, "Andhra Pradesh")["status"] == "eligible")
        r = result_for(track, 20, 1, "Andhra Pradesh")
        check("Closed job: still eligible, with a 'has passed' note",
              r["status"] == "eligible" and any("has passed" in x["text"] for x in r["reasons"]))
        check("AP post for an out-of-state user needs verification", result_for(group2, 25, 4, "Telangana")["status"] == "verify")
        check("AP post for an AP graduate is eligible", result_for(group2, 25, 4, "Andhra Pradesh")["status"] == "eligible")
        check("Graduate is not eligible for a Post Graduate post", result_for(stat_inv, 25, 4, "Andhra Pradesh")["status"] == "not_eligible")
        check("Post Graduate in a subject-specific post needs verification", result_for(stat_inv, 25, 5, "Andhra Pradesh")["status"] == "verify")

        # ================= Job finder pages =================
        client = app.test_client()

        r = client.get("/jobs")
        html = r.get_data(as_text=True)
        check("Jobs page loads", r.status_code == 200)
        check("Default sort: soonest open deadline is on page 1", "Auditor" in html and "Station Master" in html)
        check("Default sort: closed job is not on page 1", "Track Maintainer" not in html)
        check("Default sort: latest deadline is not on page 1", "Multi Tasking Staff" not in html)
        check("Pagination: page 2 shows the closed job",
              "Track Maintainer" in client.get("/jobs?page=2").get_data(as_text=True))
        check("Page number beyond the end is handled", client.get("/jobs?page=999").status_code == 200)
        check("Non-numeric page number is handled", client.get("/jobs?page=abc").status_code == 200)

        html = client.get("/jobs?q=CLERK").get_data(as_text=True)
        check("Search is case-insensitive and finds clerks",
              "Lower Division Clerk" in html and "Junior Clerk" in html and "Station Master" not in html)
        html = client.get("/jobs?q=staff+selection").get_data(as_text=True)
        check("Search also matches the organization", "Auditor" in html and "Station Master" not in html)
        html = client.get("/jobs?q=%25").get_data(as_text=True)
        check("A % in the search text is treated literally", "No jobs match" in html)
        r = client.get("/jobs?q=%27+OR+1%3D1+--")
        check("SQL-injection style text is harmless", r.status_code == 200 and "No jobs match" in r.get_data(as_text=True))

        html = client.get("/jobs?govt=Andhra+Pradesh").get_data(as_text=True)
        check("Filter: Andhra Pradesh only", "Group-II Executive" in html and "Station Master" not in html)
        html = client.get("/jobs?category=Railway").get_data(as_text=True)
        check("Filter: Railway category", "Station Master" in html and "Auditor" not in html)
        html = client.get("/jobs?qualification=1").get_data(as_text=True)
        check("Filter: qualification level 1", "Multi Tasking Staff" in html and "Auditor" not in html)
        html = client.get("/jobs?deadline=closed").get_data(as_text=True)
        check("Filter: closed deadlines", "Track Maintainer" in html and "Station Master" not in html)
        html = client.get("/jobs?deadline=open").get_data(as_text=True)
        check("Filter: open deadlines hides closed jobs", "Track Maintainer" not in html and "Station Master" in html)
        html = client.get("/jobs?deadline=week").get_data(as_text=True)
        check("Filter: closing within 7 days finds nothing in sample data", "No jobs match" in html)
        html = client.get(f"/jobs?exam={ssc_cgl['id']}").get_data(as_text=True)
        check("Filter: by recruitment exam (job_exams mapping)", "Auditor" in html and "Station Master" not in html)
        html = client.get("/jobs?sort=deadline_desc").get_data(as_text=True)
        check("Sort: latest deadline first",
              0 <= html.find("Multi Tasking Staff") < html.find("Statistical Investigator"))
        check("Invalid filter and sort values are ignored",
              client.get("/jobs?govt=Mars&sort=DROP+TABLE&qualification=99").status_code == 200)

        # ================= Job details =================
        r = client.get(f"/jobs/{auditor['id']}")
        html = r.get_data(as_text=True)
        check("Job details page loads", r.status_code == 200 and "Auditor" in html)
        check("Demo record warning is shown", "Demonstration record" in html)
        check("Official link opens in a new tab safely", 'rel="noopener noreferrer"' in html)
        check("Related jobs share the same exam", "Inspector (Taxation)" in html)
        check("Anonymous user sees a prompt instead of a result", "Open eligibility checker" in html)
        html = client.get(f"/jobs/{station['id']}").get_data(as_text=True)
        check("Job without a stored link says so", "No official application link is stored" in html)
        check("Unknown job gives 404", client.get("/jobs/99999").status_code == 404)

        # ================= Eligibility page =================
        r = client.get("/eligibility")
        check("Eligibility page loads", r.status_code == 200)
        html = client.get("/eligibility?age=25&qualification=4&state=Andhra+Pradesh").get_data(as_text=True)
        check("Eligibility results are shown", "Jobs checked" in html and "Eligible" in html)
        check("Disclaimer about the official notification is shown",
              "must be verified using the official recruitment notification" in " ".join(html.split()))
        check("Closed jobs are hidden by default", "Track Maintainer" not in html)
        html = client.get("/eligibility?age=25&qualification=4&state=Andhra+Pradesh&include_closed=1").get_data(as_text=True)
        check("Closed jobs appear when requested", "Track Maintainer" in html)
        html = client.get("/eligibility?age=25&qualification=1&state=Andhra+Pradesh&show=not_eligible").get_data(as_text=True)
        check("'Not eligible only' view works", "Not eligible" in html and "Qualification requirement not satisfied" in html)
        html = client.get("/eligibility?age=5&qualification=4&state=Andhra+Pradesh").get_data(as_text=True)
        check("Invalid age shows a validation error", "Age must be a whole number" in html)
        html = client.get("/eligibility?age=25&qualification=9&state=Nowhere").get_data(as_text=True)
        check("Invalid qualification and state are rejected",
              "Please select your highest qualification" in html and "Please select your state" in html)
        r = client.get("/eligibility?use_profile=1")
        check("'Use my profile' needs login", r.status_code == 302 and "/login" in r.headers["Location"])

        # ================= Bookmarks =================
        anon = app.test_client()
        r = anon.post(f"/jobs/{auditor['id']}/save", data={"next": "/jobs"})
        check("Saving while logged out redirects to login", r.status_code == 302 and "/login" in r.headers["Location"])
        check("Saved jobs page is protected", anon.get("/saved-jobs").status_code == 302)

        client.post("/login", data={"email": "demo@example.com", "password": "Demo@1234"})
        html = client.get(f"/jobs/{auditor['id']}").get_data(as_text=True)
        check("Logged-in user sees their own eligibility result", "Your eligibility" in html and "Qualification matches" in html)
        html = client.get("/eligibility").get_data(as_text=True)
        from utils import calculate_age
        check("Eligibility form is pre-filled from the profile",
              f'value="{calculate_age("2002-05-15")}"' in html)
        check("'Use my profile' works", client.get("/eligibility?use_profile=1").status_code == 200)

        r = client.post(f"/jobs/{auditor['id']}/save", data={"next": "/jobs"})
        check("Save redirects back to the page", r.status_code == 302 and r.headers["Location"].endswith("/jobs"))
        with standalone_db(db_path) as conn:
            saved = query_db("SELECT * FROM saved_jobs WHERE user_id = ? AND job_id = ?",
                             (demo_user["id"], auditor["id"]), conn=conn)
        check("Saved job is stored in the database", len(saved) == 1)
        check("Saved jobs page lists it", "Auditor" in client.get("/saved-jobs").get_data(as_text=True))
        check("Jobs list shows a filled bookmark", "bi-bookmark-fill" in client.get("/jobs").get_data(as_text=True))

        r = client.post(f"/jobs/{auditor['id']}/save", data={"next": "//evil.com"})
        check("Open redirect is blocked after unsave", r.status_code == 302 and "evil" not in r.headers["Location"])
        with standalone_db(db_path) as conn:
            saved = query_db("SELECT * FROM saved_jobs WHERE user_id = ? AND job_id = ?",
                             (demo_user["id"], auditor["id"]), conn=conn)
        check("Second click removes the bookmark", len(saved) == 0)
        check("Empty saved list shows a friendly message",
              "You have not saved any jobs yet" in client.get("/saved-jobs").get_data(as_text=True))
        check("Saving an unknown job gives 404", client.post("/jobs/99999/save", data={}).status_code == 404)

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()