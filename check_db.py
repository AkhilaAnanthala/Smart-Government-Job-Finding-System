"""check_db.py - prints table counts and checks that relationships are consistent."""
from db import standalone_db, query_db, count_rows, ALL_TABLES

with standalone_db() as conn:
    print("Row counts:")
    for table in ALL_TABLES:
        print(f"  {table:<20} {count_rows(table, conn=conn)}")

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("\nForeign key problems:", len(problems))

    print("\nJobs per exam (shows many jobs sharing one exam):")
    rows = query_db(
        """SELECT e.short_code, COUNT(je.job_id) AS jobs
           FROM exams e LEFT JOIN job_exams je ON je.exam_id = e.id
           GROUP BY e.id ORDER BY e.short_code""", conn=conn)
    for r in rows:
        print(f"  {r['short_code']:<12} {r['jobs']} job(s)")

    print("\nQuestions per mock test:")
    rows = query_db(
        """SELECT m.title, COUNT(q.id) AS questions
           FROM mock_tests m LEFT JOIN questions q ON q.subject_id = m.subject_id
           GROUP BY m.id""", conn=conn)
    for r in rows:
        print(f"  {r['title']:<55} {r['questions']}")