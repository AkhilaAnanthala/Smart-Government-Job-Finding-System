-- =====================================================================
-- Smart Government Job Finder and Preparation Portal
-- SQLite schema. Foreign keys are enabled per connection in db.py
-- using: PRAGMA foreign_keys = ON;
-- Dates are stored as TEXT in ISO format (YYYY-MM-DD).
-- =====================================================================

-- 1. USERS -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT    NOT NULL,
    email               TEXT    NOT NULL UNIQUE,
    password_hash       TEXT    NOT NULL,
    date_of_birth       TEXT    NOT NULL,                 -- YYYY-MM-DD
    highest_qualification TEXT  NOT NULL,                 -- label from config.QUALIFICATION_LEVELS
    state               TEXT    NOT NULL,
    district            TEXT    NOT NULL,
    preferred_category  TEXT,                             -- e.g. SSC, UPSC, APPSC, Railway
    role                TEXT    NOT NULL DEFAULT 'user'
                        CHECK (role IN ('user', 'admin')),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 2. EXAMS (recruitment examinations) ----------------------------------
CREATE TABLE IF NOT EXISTS exams (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,          -- e.g. SSC Combined Graduate Level
    short_code          TEXT    NOT NULL UNIQUE,          -- e.g. SSC-CGL
    category            TEXT    NOT NULL
                        CHECK (category IN ('UPSC', 'SSC', 'Railway', 'APPSC', 'Other')),
    conducting_body     TEXT    NOT NULL,
    govt_level          TEXT    NOT NULL
                        CHECK (govt_level IN ('Central', 'Andhra Pradesh')),
    description         TEXT,
    exam_pattern        TEXT,                             -- stages, marks, negative marking
    syllabus_summary    TEXT,
    official_url        TEXT                              -- official exam/syllabus page
);

-- 3. JOBS ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    title                   TEXT    NOT NULL,
    organization            TEXT    NOT NULL,
    govt_category           TEXT    NOT NULL
                            CHECK (govt_category IN ('Central', 'Andhra Pradesh')),
    exam_category           TEXT    NOT NULL
                            CHECK (exam_category IN ('UPSC', 'SSC', 'Railway', 'APPSC', 'Other')),
    required_qualification  TEXT    NOT NULL,             -- display text
    min_qualification_level INTEGER NOT NULL
                            CHECK (min_qualification_level BETWEEN 1 AND 5),
    min_age                 INTEGER CHECK (min_age IS NULL OR min_age >= 14),
    max_age                 INTEGER CHECK (max_age IS NULL OR max_age <= 70),
    state_requirement       TEXT,                         -- NULL = open to all states
    vacancies               INTEGER CHECK (vacancies IS NULL OR vacancies >= 0),
    vacancies_note          TEXT,                         -- e.g. 'Sample figure, not official'
    application_start       TEXT,                         -- YYYY-MM-DD or NULL
    application_deadline    TEXT,                         -- YYYY-MM-DD or NULL
    salary                  TEXT,                         -- pay scale as text
    description             TEXT,
    eligibility_text        TEXT,
    syllabus_pattern        TEXT,
    notification_url        TEXT,
    apply_url               TEXT,
    age_relaxation_verified INTEGER NOT NULL DEFAULT 0
                            CHECK (age_relaxation_verified IN (0, 1)),
    is_demo                 INTEGER NOT NULL DEFAULT 1
                            CHECK (is_demo IN (0, 1)),
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (min_age IS NULL OR max_age IS NULL OR min_age <= max_age)
);

-- 4. JOB_EXAMS (many-to-many: jobs <-> exams) ----------------------------
CREATE TABLE IF NOT EXISTS job_exams (
    job_id   INTEGER NOT NULL,
    exam_id  INTEGER NOT NULL,
    PRIMARY KEY (job_id, exam_id),
    FOREIGN KEY (job_id)  REFERENCES jobs(id)  ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

-- 5. SUBJECTS -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    description TEXT,
    UNIQUE (exam_id, name),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

-- 6. STUDY_MATERIALS ------------------------------------------------------
CREATE TABLE IF NOT EXISTS study_materials (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id    INTEGER NOT NULL,
    title         TEXT    NOT NULL,
    description   TEXT,
    resource_type TEXT    NOT NULL
                  CHECK (resource_type IN ('PDF', 'Link', 'Video', 'Notes')),
    url           TEXT,                                   -- external link
    file_path     TEXT,                                   -- safe filename inside uploads/materials/
    is_official   INTEGER NOT NULL DEFAULT 0
                  CHECK (is_official IN (0, 1)),
    added_by      INTEGER,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (url IS NOT NULL OR file_path IS NOT NULL),
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by)   REFERENCES users(id)    ON DELETE SET NULL
);

-- 7. PREVIOUS_PAPERS -------------------------------------------------------
CREATE TABLE IF NOT EXISTS previous_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    year        INTEGER CHECK (year IS NULL OR year BETWEEN 1990 AND 2100),
    url         TEXT,
    file_path   TEXT,
    is_official INTEGER NOT NULL DEFAULT 0
                CHECK (is_official IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (url IS NOT NULL OR file_path IS NOT NULL),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

-- 8. OFFICIAL_RESOURCES (admin-editable official links) ---------------------
CREATE TABLE IF NOT EXISTS official_resources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    description TEXT,
    resource_kind TEXT  NOT NULL DEFAULT 'Portal'
                CHECK (resource_kind IN ('Portal', 'Mock Test', 'Syllabus', 'Previous Papers', 'Notification')),
    exam_id     INTEGER,                                  -- NULL = general resource
    last_verified TEXT,                                   -- date admin last checked link
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE SET NULL
);

-- 9. QUESTIONS (practice question bank) -------------------------------------
CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER NOT NULL,
    question_text   TEXT    NOT NULL,
    option_a        TEXT    NOT NULL,
    option_b        TEXT    NOT NULL,
    option_c        TEXT    NOT NULL,
    option_d        TEXT    NOT NULL,
    correct_option  TEXT    NOT NULL
                    CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    explanation     TEXT,
    difficulty      TEXT    NOT NULL DEFAULT 'Medium'
                    CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
    is_demo         INTEGER NOT NULL DEFAULT 1
                    CHECK (is_demo IN (0, 1)),
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

-- 10. MOCK_TESTS ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mock_tests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    exam_id          INTEGER NOT NULL,
    subject_id       INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 10
                     CHECK (duration_minutes BETWEEN 1 AND 180),
    num_questions    INTEGER NOT NULL DEFAULT 10
                     CHECK (num_questions BETWEEN 1 AND 100),
    is_active        INTEGER NOT NULL DEFAULT 1
                     CHECK (is_active IN (0, 1)),
    UNIQUE (exam_id, subject_id),
    FOREIGN KEY (exam_id)    REFERENCES exams(id)    ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

-- 11. TEST_ATTEMPTS ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_attempts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL,
    mock_test_id       INTEGER NOT NULL,
    started_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    submitted_at       TEXT,
    total_questions    INTEGER NOT NULL DEFAULT 0,
    correct_count      INTEGER NOT NULL DEFAULT 0,
    score_percent      REAL    NOT NULL DEFAULT 0,
    time_taken_seconds INTEGER,
    status             TEXT    NOT NULL DEFAULT 'in_progress'
                       CHECK (status IN ('in_progress', 'submitted')),
    FOREIGN KEY (user_id)      REFERENCES users(id)      ON DELETE CASCADE,
    FOREIGN KEY (mock_test_id) REFERENCES mock_tests(id) ON DELETE CASCADE
);

-- 12. USER_ANSWERS --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id      INTEGER NOT NULL,
    question_id     INTEGER NOT NULL,
    question_order  INTEGER NOT NULL,                     -- 1, 2, 3 ... within this attempt
    selected_option TEXT
                    CHECK (selected_option IS NULL OR selected_option IN ('A', 'B', 'C', 'D')),
    is_correct      INTEGER CHECK (is_correct IS NULL OR is_correct IN (0, 1)),
    UNIQUE (attempt_id, question_id),
    FOREIGN KEY (attempt_id)  REFERENCES test_attempts(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id)     ON DELETE CASCADE
);

-- 13. SAVED_JOBS -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    job_id   INTEGER NOT NULL,
    saved_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, job_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id)  REFERENCES jobs(id)  ON DELETE CASCADE
);

-- INDEXES (speed up common searches) ---------------------------------------------
CREATE INDEX IF NOT EXISTS idx_jobs_deadline      ON jobs(application_deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_category      ON jobs(govt_category, exam_category);
CREATE INDEX IF NOT EXISTS idx_subjects_exam      ON subjects(exam_id);
CREATE INDEX IF NOT EXISTS idx_materials_subject  ON study_materials(subject_id);
CREATE INDEX IF NOT EXISTS idx_papers_exam        ON previous_papers(exam_id);
CREATE INDEX IF NOT EXISTS idx_questions_subject  ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_attempts_user      ON test_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_answers_attempt    ON user_answers(attempt_id);
CREATE INDEX IF NOT EXISTS idx_saved_user         ON saved_jobs(user_id);