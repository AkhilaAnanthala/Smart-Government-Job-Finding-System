"""run_all_checks.py - runs every test script and summarises the results."""
import os
import re
import subprocess
import sys

SCRIPTS = ["check_auth.py", "check_public.py", "check_jobs.py", "check_prep.py",
           "check_tests.py", "check_admin.py", "test_workflows.py"]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    all_ok = True
    for script in SCRIPTS:
        if not os.path.isfile(script):
            print(f"MISSING  {script}")
            all_ok = False
            continue
        proc = subprocess.run([sys.executable, script], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        match = re.search(r"(\d+) of (\d+) checks passed", proc.stdout)
        fails = [line for line in proc.stdout.splitlines() if line.startswith("FAIL")]
        if match and match.group(1) == match.group(2) and not fails and proc.returncode == 0:
            print(f"OK       {script:<20} {match.group(1)} of {match.group(2)} checks passed")
            continue
        all_ok = False
        print(f"PROBLEM  {script}")
        for line in fails:
            print("         " + line)
        if not match:
            print("         The script crashed. Last lines of its error message:")
            for line in proc.stderr.strip().splitlines()[-8:]:
                print("         " + line)
    print("\nAll checks passed." if all_ok else "\nSome checks need attention (see above).")


if __name__ == "__main__":
    main()