"""check_auth.py - tests registration, login, profile update and logout logic."""
import os
import tempfile

from app import create_app
from db import standalone_db, query_db

results = []


def check(name, condition):
    results.append(condition)
    print(("PASS  " if condition else "FAIL  ") + name)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        app = create_app({"DATABASE_PATH": db_path, "WTF_CSRF_ENABLED": False, "TESTING": True})
        client = app.test_client()

        form = {
            "full_name": "Test Student", "email": "Test@Example.com", "password": "Test@1234",
            "confirm_password": "Test@1234", "date_of_birth": "2000-01-01",
            "highest_qualification": "Graduate (Bachelor's Degree)", "state": "Andhra Pradesh",
            "district": "Guntur", "preferred_category": "SSC",
        }

        r = client.post("/register", data=form)
        check("Register redirects to login", r.status_code == 302 and "/login" in r.headers["Location"])

        with standalone_db(db_path) as conn:
            user = query_db("SELECT * FROM users WHERE email = ?", ("test@example.com",), one=True, conn=conn)
        check("User saved with lower-case email", user is not None)
        check("Password is hashed, not plain text",
              user["password_hash"] != "Test@1234" and user["password_hash"].startswith(("scrypt:", "pbkdf2:")))
        check("New users get the 'user' role", user["role"] == "user")

        r = client.post("/login", data={"email": "test@example.com", "password": "Test@1234"})
        check("Login succeeds with redirect", r.status_code == 302)
        with client.session_transaction() as s:
            check("Session holds the user id", s.get("user_id") == user["id"])

        r = client.post("/profile", data={**form, "action": "update_profile", "district": "Vijayawada"})
        with standalone_db(db_path) as conn:
            updated = query_db("SELECT district FROM users WHERE id = ?", (user["id"],), one=True, conn=conn)
        check("Profile update saved", r.status_code == 302 and updated["district"] == "Vijayawada")

        r = client.post("/profile", data={"action": "change_password", "current_password": "Test@1234",
                                          "new_password": "NewPass@5678", "confirm_new_password": "NewPass@5678"})
        check("Password change redirects", r.status_code == 302)

        r = client.post("/logout")
        check("Logout redirects to login", r.status_code == 302 and "/login" in r.headers["Location"])
        with client.session_transaction() as s:
            check("Session is cleared after logout", "user_id" not in s)

        r = client.get("/profile")
        check("Profile is protected when logged out", r.status_code == 302 and "/login" in r.headers["Location"])

        r = client.post("/login?next=//evil.com", data={"email": "test@example.com", "password": "NewPass@5678"})
        check("Open redirect is blocked", r.status_code == 302 and "evil" not in r.headers["Location"])
        client.post("/logout")

        r = client.post("/login?next=/profile", data={"email": "test@example.com", "password": "NewPass@5678"})
        check("Safe next URL is honoured", r.headers["Location"].endswith("/profile"))

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()