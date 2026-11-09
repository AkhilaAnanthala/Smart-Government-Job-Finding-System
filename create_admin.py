"""
create_admin.py
Secure way to create the first administrator (or promote an existing user).

Usage (venv active):   python create_admin.py

The password is typed with hidden input and stored only as a hash.
No admin password exists anywhere in the source code.
"""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

import db
from config import QUALIFICATION_LEVELS
from utils import is_valid_email, password_error

# Placeholder profile values. The admin can edit them later on the Profile page.
PLACEHOLDER_DOB = "1990-01-01"
PLACEHOLDER_STATE = "Andhra Pradesh"
PLACEHOLDER_DISTRICT = "Administration"


def create_admin(conn, full_name, email, password):
    """Create a new administrator. Raises ValueError with a readable message on bad input."""
    name = " ".join(full_name.split())
    email = email.strip().lower()

    if not 2 <= len(name) <= 100:
        raise ValueError("Name must be 2 to 100 characters.")
    if not all(ch.isalpha() or ch in " .'-" for ch in name):
        raise ValueError("Name may contain only letters, spaces, dots, hyphens and apostrophes.")
    if not is_valid_email(email):
        raise ValueError("Please enter a valid email address.")
    problem = password_error(password)
    if problem:
        raise ValueError(problem)
    if db.get_user_by_email(email, conn=conn):
        raise ValueError("An account with this email already exists. Run the script again "
                         "and choose to promote it.")

    return db.create_user(
        full_name=name, email=email, password_hash=generate_password_hash(password),
        date_of_birth=PLACEHOLDER_DOB, highest_qualification=QUALIFICATION_LEVELS[4],
        state=PLACEHOLDER_STATE, district=PLACEHOLDER_DISTRICT,
        preferred_category=None, role="admin", conn=conn)


def promote_to_admin(conn, email):
    """Give an existing user the admin role. Raises ValueError if that is not possible."""
    user = db.get_user_by_email(email, conn=conn)
    if user is None:
        raise ValueError("No account with this email exists.")
    if user["role"] == "admin":
        raise ValueError("This account is already an administrator.")
    db.execute_db("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],), conn=conn)
    return user["id"]


def main():
    db.init_db()   # makes sure the tables exist (does nothing if they do)

    default_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    prompt = f"Admin email [{default_email}]: " if default_email else "Admin email: "
    email = input(prompt).strip().lower() or default_email
    if not email:
        print("Error: an email is required.")
        sys.exit(1)

    with db.standalone_db() as conn:
        try:
            existing = db.get_user_by_email(email, conn=conn)
            if existing:
                print(f"An account for {email} already exists ({existing['full_name']}, role: {existing['role']}).")
                answer = input("Promote this account to administrator? (yes/no): ").strip().lower()
                if answer != "yes":
                    print("Cancelled. Nothing was changed.")
                    return
                promote_to_admin(conn, email)
                print("Done. That account is now an administrator.")
            else:
                name = input("Full name: ")
                password = getpass.getpass("Password (hidden): ")
                if password != getpass.getpass("Confirm password: "):
                    print("Error: the passwords do not match.")
                    sys.exit(1)
                create_admin(conn, name, email, password)
                print("Done. Administrator created. Log in at http://127.0.0.1:5000/login")
        except ValueError as err:
            print(f"Error: {err}")
            sys.exit(1)


if __name__ == "__main__":
    main()