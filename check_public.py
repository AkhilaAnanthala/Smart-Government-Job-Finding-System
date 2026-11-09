"""check_public.py - tests the home page, auth pages, static files, error pages and CSRF."""
import os
import re
import tempfile

import seed_data
from app import create_app
from db import standalone_db

results = []


def check(name, condition):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name)


def get_token(client):
    """Read the CSRF token from the <meta> tag of the home page."""
    html = client.get("/").get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else ""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        app = create_app({"DATABASE_PATH": db_path, "TESTING": True})  # CSRF stays ON

        with standalone_db(db_path) as conn:
            seed_data.seed_exams(conn)
            seed_data.seed_subjects(conn)
            seed_data.seed_jobs(conn)
            seed_data.seed_resources(conn)
            seed_data.seed_questions_and_tests(conn)
            seed_data.seed_demo_user(conn)

        client = app.test_client()

        # ---- Public pages ----
        r = client.get("/")
        html = r.get_data(as_text=True)
        check("Home page loads (200)", r.status_code == 200)
        check("Home shows 'Latest Job Notifications'", "Latest Job Notifications" in html)
        check("Home shows 'Popular Examinations'", "Popular Examinations" in html)
        check("Demo jobs are labelled 'Demo data'", "Demo data" in html)
        check("Disclaimer is in the footer", "not official notifications" in html)
        check("CSRF meta tag is present", 'name="csrf-token"' in html)
        check("Login page loads", client.get("/login").status_code == 200)
        check("Register page loads", client.get("/register").status_code == 200)

        r = client.get("/does-not-exist")
        check("Unknown URL gives a styled 404 page", r.status_code == 404 and "Page not found" in r.get_data(as_text=True))
        check("CSS file is served", client.get("/static/css/style.css").status_code == 200)
        check("JS file is served", client.get("/static/js/main.js").status_code == 200)
        check("Profile redirects when logged out", client.get("/profile").status_code == 302)

        # ---- Registration validation ----
        r = client.post("/register", data={"csrf_token": get_token(client), "full_name": "", "email": "bad"})
        check("Invalid registration shows field errors", r.status_code == 200 and "invalid-feedback" in r.get_data(as_text=True))

        # ---- CSRF protection ----
        r = client.post("/login", data={"email": "demo@example.com", "password": "Demo@1234"})
        with client.session_transaction() as s:
            check("Login without CSRF token is rejected", r.status_code == 302 and "user_id" not in s)

        r = client.post("/login", data={"csrf_token": get_token(client), "email": "demo@example.com",
                                        "password": "Demo@1234"})
        with client.session_transaction() as s:
            check("Login with CSRF token works", r.status_code == 302 and "user_id" in s)

        # ---- Logged-in pages ----
        r = client.get("/profile")
        check("Profile page shows the user's name", r.status_code == 200 and "Demo Student" in r.get_data(as_text=True))
        check("Navbar shows Logout when logged in", "Logout" in client.get("/").get_data(as_text=True))

        client.post("/logout", data={})
        with client.session_transaction() as s:
            check("Logout without CSRF token is rejected", "user_id" in s)

        client.post("/logout", data={"csrf_token": get_token(client)})
        with client.session_transaction() as s:
            check("Logout with CSRF token clears the session", "user_id" not in s)

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()