# Smart Government Job Finder and Preparation Portal

A college **Community Service Project (CSP)** built with Python Flask and SQLite.
It helps students and job seekers find Central Government and Andhra Pradesh
Government job notifications, check their eligibility, and prepare for the
recruitment examinations.

| | |
|---|---|
| **Student** | [Your Name], [Roll Number] |
| **Course** | B.Tech Computer Science |
| **College** | [College Name] |
| **Faculty guide** | [Faculty Name] |

> **Important:** this is a prototype. The job records, vacancy numbers, dates, age
> limits and pay scales are **demonstration data**, not official notifications.
> Every such record is labelled "Demo data" on screen. Always verify details on the
> official recruitment website before applying for any real job.

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Objectives](#2-objectives)
3. [Features](#3-features)
4. [Technology stack](#4-technology-stack)
5. [Architecture](#5-architecture)
6. [Database design](#6-database-design)
7. [Project folder structure](#7-project-folder-structure)
8. [Installation (Windows + VS Code)](#8-installation-windows--visual-studio-code)
9. [Running the application](#9-running-the-application)
10. [Creating the first administrator](#10-creating-the-first-administrator)
11. [Demo accounts](#11-demo-accounts)
12. [Using the admin panel](#12-using-the-admin-panel)
13. [How the eligibility checker works](#13-how-the-eligibility-checker-works)
14. [How the mock test works](#14-how-the-mock-test-works)
15. [Security features](#15-security-features)
16. [Testing](#16-testing)
17. [Limitations](#17-limitations)
18. [Future enhancements](#18-future-enhancements)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Problem statement

Government job information is spread across many websites. A student must
visit separate sites to find a notification, read its eligibility rules, locate
the syllabus, find previous question papers and then practise. Eligibility rules
(qualification, age, state) are written in long notifications, so many candidates
are unsure whether they can apply at all.

## 2. Objectives

- Bring job notifications, eligibility, syllabus, study resources and mock tests
  into one portal.
- Let a student search and filter jobs and save the ones they like.
- Check a student's eligibility with a transparent rule-based engine and explain
  every result.
- Organise preparation content so that **many jobs share one exam's resources**
  instead of duplicating them.
- Offer timed multiple-choice mock tests with automatic scoring and progress
  tracking.
- Give administrators a secure panel to manage all content without editing code.

## 3. Features

**For students**
- Registration, login, logout, profile editing and password change.
- Government job finder: search by title or organisation; filter by Central or
  Andhra Pradesh, exam category, qualification and deadline; sort by deadline;
  pagination.
- Job details with an official notification link and an official application link
  (both open on the external website).
- Save (bookmark) jobs.
- **Smart eligibility checker:** Eligible / Not eligible / Needs further
  verification, with reasons for each decision.
- **Preparation Hub:** exam categories (UPSC, SSC, Railway, APPSC, Other), exam
  details, syllabus and pattern, study materials (links and PDFs), previous
  question papers, practice questions with hidden answers.
- Official resources clearly marked **Official** or **Additional resource**.
- **Mock tests:** timer, previous/next navigation, question palette, autosave,
  confirmation before submit, automatic scoring, results with explanations,
  attempt history.
- Personal dashboard: matching jobs, saved jobs, upcoming deadlines, recent tests,
  average score, score chart, preparation progress.

**For administrators**
- Protected admin panel with role-based access.
- Manage users (change role, delete), jobs, exams, subjects, study materials
  (including safe PDF upload), previous papers, official links, mock tests and
  questions.
- View all mock-test results and portal statistics.
- Warnings for official links that have not been verified.

## 4. Technology stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5 (CDN), Bootstrap Icons (CDN), Chart.js (CDN) |
| Backend | Python 3.9+ and Flask |
| Database | SQLite through Python's built-in `sqlite3` module (parameterized SQL) |
| Security helpers | Werkzeug (password hashing, safe file names), Flask-WTF (CSRF protection) |
| Configuration | python-dotenv (`.env` file) |

No paid APIs and no AI services are used.
**The browser needs an internet connection** because Bootstrap, the icons and
Chart.js load from a CDN.

## 5. Architecture

```
Browser (HTML + Bootstrap + JavaScript)
        |  HTTP requests (forms, and fetch/AJAX for mock-test autosave)
        v
Flask app  (app.py)  -- sessions, CSRF protection, error pages
        |
        +-- routes_auth.py     register, login, logout, profile
        +-- routes_public.py   home page, user dashboard
        +-- routes_jobs.py     job finder, details, bookmarks, eligibility page
        +-- routes_prep.py     preparation hub, safe PDF serving
        +-- routes_tests.py    mock tests, autosave, submit, results, history
        +-- routes_admin.py    admin panel (every route needs the admin role)
        |
        +-- eligibility.py     rule-based eligibility engine (pure Python)
        +-- mock_engine.py     test timing, question selection, scoring
        +-- utils.py           login/admin decorators, validation, PDF upload
        +-- db.py              database connection and reusable helpers
        +-- config.py          settings (secrets come from .env)
        v
SQLite database  (database/portal.db)  created from schema.sql by seed_data.py
```

The code is split into small files so each has one job. For example, all
eligibility rules live in `eligibility.py` and contain no web code, which makes
them easy to explain and test.

## 6. Database design

13 tables. Foreign keys are enabled on every connection.

| Table | Purpose |
|---|---|
| `users` | Accounts (`role` is `user` or `admin`, password stored as a hash) |
| `exams` | Recruitment examinations (SSC CGL, RRB NTPC, APPSC Group-II ...) |
| `jobs` | Job records with eligibility rules (qualification level, age, state) |
| `job_exams` | **Mapping table:** many jobs can use one exam, one job can use several exams |
| `subjects` | Subjects of an exam |
| `study_materials` | Links or PDFs attached to a subject |
| `previous_papers` | Links or PDFs attached to an exam |
| `official_resources` | Admin-editable official links (portal, syllabus, mock test ...) |
| `questions` | Practice question bank (4 options, 1 correct answer, explanation) |
| `mock_tests` | A timed test for one subject of one exam |
| `test_attempts` | One row per attempt (status, score, time taken) |
| `user_answers` | The fixed set of questions of an attempt and the user's selections |
| `saved_jobs` | Bookmarks (one per user per job) |

Relationships:

```
Government Job --< job_exams >-- Exam --< Subject --< Study Material
                                  |          |
                                  |          +--< Question --< user_answers >-- test_attempts >-- user
                                  +--< Previous Paper
                                  +--< Mock Test (exam + subject) --< test_attempts
users --< saved_jobs >-- jobs
```

**Why this design:** study materials hang off *subjects* and subjects hang off
*exams*. Every job linked to an exam therefore shows the same resources, with no
duplication. Deleting a parent row removes its children through
`ON DELETE CASCADE`, so no orphan records remain.

## 7. Project folder structure

```
smart-government-job-portal/
|-- app.py                  Creates the Flask app, CSRF, error handlers
|-- config.py               Settings and lookup lists
|-- db.py                   Database helper functions
|-- utils.py                Decorators, validators, safe PDF upload
|-- eligibility.py          Eligibility rule engine
|-- mock_engine.py          Mock-test logic (timing, scoring)
|-- routes_auth.py          Register, login, logout, profile
|-- routes_public.py        Home page and dashboard
|-- routes_jobs.py          Jobs, details, bookmarks, eligibility page
|-- routes_prep.py          Preparation hub
|-- routes_tests.py         Mock tests
|-- routes_admin.py         Admin panel
|-- schema.sql              Table definitions
|-- seed_data.py            Creates the database and inserts sample data
|-- create_admin.py         Secure admin creation
|-- check_db.py             Database sanity check
|-- check_auth.py           Test: authentication
|-- check_public.py         Test: home, pages, CSRF
|-- check_jobs.py           Test: jobs, eligibility, bookmarks
|-- check_prep.py           Test: preparation hub, PDF serving
|-- check_tests.py          Test: mock tests, dashboard
|-- check_admin.py          Test: admin panel
|-- test_workflows.py       Test: the 16 end-to-end workflows
|-- run_all_checks.py       Runs every test and summarises
|-- requirements.txt        Python packages
|-- .env.example            Sample environment file (no real secrets)
|-- .gitignore
|-- README.md
|-- database/
|   `-- portal.db           Created automatically
|-- templates/
|   |-- base.html, index.html, register.html, login.html, profile.html
|   |-- dashboard.html, jobs.html, job_details.html, eligibility.html, saved_jobs.html
|   |-- preparation.html, exams.html, exam_details.html, syllabus.html
|   |-- materials.html, previous_papers.html, practice_questions.html
|   |-- mock_tests.html, take_test.html, results.html, attempt_history.html
|   |-- _job_card.html, _pagination.html, _pager.html, _eligibility_result.html,
|   |   _material_card.html, _paper_card.html, _official_resource.html,
|   |   _profile_fields.html            (small reusable pieces)
|   |-- errors/   403.html, 404.html, 500.html
|   `-- admin/    base_admin.html, _macros.html, dashboard.html, users.html,
|                 jobs.html, job_form.html, exams.html, exam_form.html,
|                 subjects.html, materials.html, material_form.html, papers.html,
|                 official_resources.html, mock_tests.html, questions.html,
|                 question_form.html, results.html
|-- static/
|   |-- css/style.css
|   |-- js/   main.js, mock_test.js, dashboard.js
|   `-- images/
`-- uploads/
    `-- materials/          Uploaded PDFs (safe, generated file names)
```

## 8. Installation (Windows + Visual Studio Code)

**Requirements:** Python 3.9 or newer (download from python.org and tick
**"Add Python to PATH"** during installation) and Visual Studio Code.

1. Open the project folder in VS Code: **File -> Open Folder**.
2. Open the terminal with **Ctrl + `** (backtick) and check Python:

   ```powershell
   python --version
   ```

3. Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```

   You should see `(venv)` at the start of the prompt.
   If PowerShell says *running scripts is disabled*, run this once and activate again:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

4. Install the packages:

   ```powershell
   pip install -r requirements.txt
   ```

5. Create your private settings file and a secret key:

   ```powershell
   copy .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Paste the printed key after `SECRET_KEY=` in `.env`. Never share or upload `.env`.

6. Create the database and load the sample data:

   ```powershell
   python seed_data.py --reset
   python check_db.py
   ```

   Sample data: 9 exams, 19 subjects, 15 demo jobs, 80 practice questions,
   8 mock tests, 5 official links and 1 demo student.
   `--reset` deletes **all** existing data, so use it only for a fresh start.
   Running `python seed_data.py` without `--reset` adds missing sample data and
   skips anything that already exists.

## 9. Running the application

```powershell
venv\Scripts\activate
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Press **Ctrl + C** in the
terminal to stop the server.

The site listens on `127.0.0.1`, so only your own laptop can open it.
Flask's built-in server is for development and demonstrations, not for
production use.

## 10. Creating the first administrator

No admin password exists anywhere in the source code. Create the admin
yourself:

```powershell
python create_admin.py
```

1. Enter an email address and a full name.
2. Type a password twice. It is hidden while you type and stored only as a hash.
   It needs at least 8 characters with letters and numbers.
3. Log in at http://127.0.0.1:5000/login. Your name in the navigation bar now has
   an **Admin Panel** link.

If the email already belongs to a registered student, the script offers to
**promote** that account instead. An administrator can also promote or demote
other users on the admin **Users** page (you cannot change your own role).

Optional: put `ADMIN_EMAIL=you@example.com` in `.env` to pre-fill the email
prompt. Do not put a password in any file.

## 11. Demo accounts

| Role | Email | Password |
|---|---|---|
| Student (demo) | `demo@example.com` | `Demo@1234` |
| Administrator | the one **you** create in section 10 | the one you choose |

The demo student exists only for local demonstrations, and the login page shows
its hint only while `FLASK_DEBUG=1`. **Delete the demo student** (Admin Panel ->
Users) and set `FLASK_DEBUG=0` before showing the project on any shared or
public machine.

## 12. Using the admin panel

Log in as an administrator and open **Admin Panel** from your name menu.

### Add a job
1. **Jobs -> Add job.**
2. Fill in the title, organisation, government (Central or Andhra Pradesh) and
   exam category.
3. Set the **minimum qualification level** (1 = 10th ... 5 = Post Graduate), the
   qualification text, minimum and maximum age and an optional state requirement.
   The eligibility checker reads these fields.
4. Enter dates (start and deadline), salary, description and syllabus text.
5. Paste the **official** notification and application links. Use real links only.
   Leave them empty if you do not have verified ones.
6. Tick the recruitment exam(s) the job uses. This fills the `job_exams` table, so
   the job automatically gets that exam's study material.
7. Leave **demonstration data** ticked unless every detail was verified against the
   official notification.

To edit or delete a job, use **Edit** or the trash button in the Jobs list.

### Add study material
1. Make sure the exam and subject exist (**Exams** and **Subjects** pages).
2. **Materials -> Add study material.** Choose the subject, a type and a title.
3. Give an **external link**, upload a **PDF** (max 5 MB), or both.
   Only real PDF files are accepted (the extension and the file content are both
   checked), and files are stored under a safe generated name.
4. Tick **Official** only for resources that really come from a government website.
5. Do **not** upload copyrighted books or other unauthorised material.

Previous papers work the same way on the **Papers** page.

### Add mock-test questions
1. **Questions -> Add question.** Choose the subject, write the question, four
   different options, the correct answer and an explanation.
2. Keep **demo** ticked for questions that are not official previous-year questions.
3. A subject needs a mock test before students can take it: **Mock tests -> Add
   mock test**, choose the subject, the duration and the number of questions. The
   exam is taken from the subject. If a subject has fewer questions than the setting
   says, the available questions are used and the overview page warns you.

### Update official links
**Official links** lists every official resource. Edit a link and the whole
site (home page, preparation hub, exam pages, mock-test page) updates with no code
change. Open each link yourself and click **Mark verified today**. Changing a link
resets it to "Not yet verified".

## 13. How the eligibility checker works

`eligibility.py` compares one profile (age, qualification, state) with the rules
stored for one job. Each rule gives a reason, and the reasons decide the result:

| Rule | Result |
|---|---|
| Qualification level lower than required | **Not eligible** |
| Age below the minimum, or state different from a stated state requirement | **Not eligible** |
| Age above the stated maximum | **Needs further verification** (relaxation may apply) |
| ITI/Diploma vs 12th pass posts, specific subject or training in the requirement, Andhra Pradesh post for another state's resident | **Needs further verification** |
| Everything matches | **Eligible** |

What it deliberately does **not** do:
- It does **not** apply category-based age relaxation, because official relaxation
  rules are not stored. Over-age candidates are told to check the notification.
- It compares the **education level** only, not the subject or trade.
- Its result is guidance. Every result page says the final decision must be
  verified using the official recruitment notification.

## 14. How the mock test works

- Starting a test picks a random, fixed set of questions for that attempt and records
  the start time. Starting the same test again resumes the unfinished attempt.
- The **server** keeps the clock. Reloading the page or closing the tab does not
  pause the timer.
- Every click is **autosaved** to the server, and the final submit also sends all
  selections.
- Correct answers and explanations are **not** sent to the browser during the test.
- Scoring happens on the server: score = correct answers divided by total questions.
  There is no negative marking, and unanswered questions score zero.
- If time runs out, the test is submitted automatically. Answers arriving long after
  the deadline are not counted.
- Results show every question with the correct answer and the explanation. History,
  the dashboard and the admin results page all read the saved attempts.
- The questions are **original practice questions made for demonstration**, not
  official previous-year questions.

## 15. Security features

- Passwords are hashed with Werkzeug and never stored as plain text.
- Sessions use secure cookie settings; the session is renewed at login.
- CSRF tokens protect every form and every autosave request.
- Roles are checked on the server for every admin route, and the role is re-read
  from the database on each request.
- All SQL uses `?` placeholders (parameterized queries), and search text is
  escaped.
- Links entered by administrators must be `http://` or `https://`, which blocks
  `javascript:` links.
- Uploads are limited to 5 MB, must be real PDFs and get safe, unique file names.
  Files are served only by their stored name, which blocks `../` path tricks.
- Login redirects are limited to this website (no open redirects), and five failed
  logins lock that email and address for five minutes.
- The secret key comes from `.env`, which is excluded from Git.

## 16. Testing

Run every automated test with one command:

```powershell
python run_all_checks.py
```

Each test script uses a **temporary database and upload folder**, so your real data
is never touched. You can also run them one by one:

| Script | What it tests |
|---|---|
| `check_auth.py` | Registration, hashing, login, logout, profile, open-redirect protection |
| `check_public.py` | Home page, static files, error pages, CSRF protection |
| `check_jobs.py` | Search, filters, sorting, pagination, eligibility rules, bookmarks |
| `check_prep.py` | Preparation pages, filters, PDF open/download, path-traversal protection |
| `check_tests.py` | Mock tests, autosave, scoring, time limit, access control, dashboard |
| `check_admin.py` | `create_admin.py`, every admin workflow, PDF safety, cascades |
| `test_workflows.py` | The 16 workflows below, end to end, with real CSRF tokens |

A script is healthy when every line says `PASS` and the last line shows two equal
numbers, for example `120 of 120 checks passed.`

### The 16 end-to-end workflows

| # | Workflow |
|---|---|
| 1 | Register a new user |
| 2 | Log in and log out |
| 3 | Update the user profile |
| 4 | Search and filter government jobs |
| 5 | Open a job details page |
| 6 | Check eligibility for a job |
| 7 | Save a job |
| 8 | Open study materials |
| 9 | Access previous-paper links |
| 10 | Start and submit a mock test |
| 11 | View the score and explanations |
| 12 | Verify that the test attempt is saved |
| 13 | Log in as an administrator |
| 14 | Add or edit a job |
| 15 | Add study material and mock-test questions |
| 16 | Verify that normal users cannot access admin functions |

### Manual test checklist

1. Register a student, log in, change the profile and log out.
2. On **Jobs**, try every filter and the sort, open a job and check its eligibility.
3. Save a job and find it under **Saved Jobs**.
4. Open **Preparation -> Examinations -> an exam** and follow Syllabus, Materials and
   Previous Papers.
5. Take a mock test: answer, move with Previous/Next, reload the page, submit, read
   the explanations and open **Test History**.
6. Log in as the admin, add a job, a study material (with a PDF) and a question,
   then check that students can see them.
7. Log in as a normal user and open `/admin`. You must see "Access denied (403)".

## 17. Limitations

- The job, vacancy, date, age and pay data are **samples**. The portal does not
  cover every government job in India, and nothing is fetched live from official
  websites.
- Official links were configured from addresses provided for the project. Each one
  shows "Not yet verified" until an administrator opens it and marks it verified.
  For some exams (Railway Recruitment Boards, AP DSC) no official link is stored,
  and the pages say so.
- The eligibility checker compares education level, age and state only. It does not
  apply category-based age relaxation, physical standards, domicile rules, subject
  requirements or other conditions.
- Mock tests have no negative marking, no per-section timing and no question
  shuffling inside an attempt beyond the initial random selection.
- The failed-login lock is kept in memory and resets when the server restarts.
- There is no email verification, password reset or notification system.
- SQLite and Flask's development server suit a demonstration and a small number of
  users, not a large public deployment.
- Bootstrap, icons and Chart.js load from a CDN, so an internet connection is needed.
- The user interface is in English only.

## 18. Future enhancements

- Import real notifications from official sources after verification, and an admin
  workflow to mark records as verified.
- Rules for category-based age relaxation, loaded from official notification data.
- Email or SMS alerts for new jobs and approaching deadlines.
- Email verification and password reset.
- Negative marking, section-wise timing and full-length mock tests.
- Personalised study plans and weak-topic analysis from test history.
- Telugu and Hindi language support.
- Deployment on a production server with a production database.
- Exporting results and job lists as PDF or Excel files.

## 19. Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognised | Reinstall Python and tick **Add Python to PATH**, then reopen VS Code |
| `ModuleNotFoundError: flask` (or `dotenv`, `flask_wtf`) | Activate the virtual environment (`venv\Scripts\activate`) and run `pip install -r requirements.txt` |
| "running scripts is disabled" | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `Address already in use` | An earlier server is still running. Press Ctrl+C in that terminal or close it |
| `no such table` error | Run `python seed_data.py --reset` |
| `TemplateNotFound` | A template is in the wrong folder. Admin pages go in `templates/admin/`, error pages in `templates/errors/` |
| Page looks unstyled, no icons | You are offline. Bootstrap loads from a CDN |
| "Your session expired or the form was invalid" | Reload the page and submit again. Every form needs its `csrf_token` field |
| Upload rejected | Only real PDF files up to 5 MB are accepted |
| Red squiggles in templates in VS Code | The editor does not understand Jinja tags. Install the **Better Jinja** extension; the site is not affected |
| A test script prints `FAIL` | Run that script alone and read the failing line. Fix the file it names, then run `python run_all_checks.py` again |

## Disclaimer

This portal is an educational prototype. It is not affiliated with UPSC, SSC,
the Railway Recruitment Boards, APPSC or any government body. Job details shown
as "Demo data" are samples. Verify dates, vacancies, eligibility and application
links on the official recruitment website before applying.