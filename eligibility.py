"""
eligibility.py
Rule-based eligibility engine.

check_job_eligibility(job, age, qualification_level, state) compares a user's
profile with the rules stored for ONE job and returns:

    {
      "status":    "eligible" | "verify" | "not_eligible",
      "label":     text to show, "css_class": Bootstrap colour, "icon": icon class,
      "reasons":   [ {"kind": "ok"|"fail"|"warn"|"info", "text": "..."}, ... ]
    }

Rules of the engine:
  * Only rules stored in the database are used. Nothing is guessed.
  * Category-based age relaxation is NOT applied, because the official relaxation
    rules are not stored. Over-age users get "verify", never a false "eligible".
  * The result is guidance only. The official notification always decides.
"""
import re
from datetime import date

from config import QUALIFICATION_LABEL_TO_LEVEL, QUALIFICATION_LEVELS
from utils import calculate_age, format_date, parse_date

STATUS_ELIGIBLE = "eligible"
STATUS_VERIFY = "verify"
STATUS_NOT_ELIGIBLE = "not_eligible"

STATUS_DISPLAY = {
    STATUS_ELIGIBLE: {"label": "Eligible", "css_class": "success", "icon": "bi-check-circle-fill"},
    STATUS_VERIFY: {"label": "Needs further verification", "css_class": "warning",
                    "icon": "bi-exclamation-triangle-fill"},
    STATUS_NOT_ELIGIBLE: {"label": "Not eligible", "css_class": "danger", "icon": "bi-x-circle-fill"},
}

# Words in a qualification text that suggest a subject, trade or training requirement
# which a simple level comparison cannot verify.
SPECIFIC_REQUIREMENT_PATTERN = re.compile(r"\b(with|d\.el\.ed|statistics|typing)\b", re.IGNORECASE)


def _reason(kind, text):
    return {"kind": kind, "text": text}


# --------------------------------------------------------------------
# Profile helper
# --------------------------------------------------------------------
def profile_from_user(user):
    """Return (age, qualification_level, state) from a users-table row."""
    age = calculate_age(user["date_of_birth"])
    level = QUALIFICATION_LABEL_TO_LEVEL.get(user["highest_qualification"])
    return age, level, user["state"]


# --------------------------------------------------------------------
# Individual rules (each returns a list of reasons)
# --------------------------------------------------------------------
def _check_qualification(job, user_level):
    job_level = job["min_qualification_level"]
    job_text = job["required_qualification"]

    if user_level not in QUALIFICATION_LEVELS:
        return [_reason("warn", "Your qualification is not recorded, so it could not be compared.")]

    user_label = QUALIFICATION_LEVELS[user_level]
    reasons = []

    if job_level == 3:
        # ITI / Diploma / teacher-training posts are not a simple step on the ladder.
        if user_level < 3:
            reasons.append(_reason(
                "fail", f"Qualification requirement not satisfied: this post needs {job_text}, "
                        f"but your highest qualification is {user_label}."))
        elif user_level == 3:
            reasons.append(_reason("ok", f"Qualification level matches: {user_label}."))
        else:
            reasons.append(_reason(
                "warn", f"This post asks for {job_text}. Whether a higher qualification "
                        f"({user_label}) is accepted depends on the official notification."))
    elif user_level == 3 and job_level == 2:
        reasons.append(_reason(
            "warn", "Whether an ITI/Diploma is accepted in place of 12th pass depends on the "
                    "official notification."))
    elif user_level >= job_level:
        reasons.append(_reason(
            "ok", f"Qualification matches: your {user_label} meets the requirement ({job_text})."))
    else:
        reasons.append(_reason(
            "fail", f"Qualification requirement not satisfied: this post needs {job_text}, "
                    f"but your highest qualification is {user_label}."))

    # Only mention subject/trade hints when the level itself is not a failure.
    if reasons[0]["kind"] != "fail" and SPECIFIC_REQUIREMENT_PATTERN.search(job_text):
        reasons.append(_reason(
            "warn", f"The requirement says '{job_text}'. A specific subject, trade or training may "
                    f"be needed. This checker compares only the education level."))
    return reasons


def _check_age(job, age):
    min_age, max_age = job["min_age"], job["max_age"]

    if min_age is None and max_age is None:
        return [_reason("info", "No age limit is stored for this post. Check the official notification.")]
    if age is None:
        return [_reason("warn", "Your age could not be determined, so it could not be compared.")]

    if min_age is not None and age < min_age:
        return [_reason("fail", f"Age requirement not satisfied: you are {age}, "
                                f"but the minimum age is {min_age}.")]
    if max_age is not None and age > max_age:
        return [_reason(
            "warn", f"Your age ({age}) is above the stated general upper limit ({max_age}). Some "
                    f"categories get age relaxation, but this portal does not apply it because the "
                    f"official rules are not stored. Check the official notification.")]

    if min_age is not None and max_age is not None:
        limit = f"{min_age} to {max_age}"
    elif max_age is not None:
        limit = f"up to {max_age}"
    else:
        limit = f"{min_age} or above"
    return [_reason("ok", f"Age appears to be within the stated general range ({limit} years). "
                          f"You are {age}. Category-based relaxation is not applied.")]


def _check_state(job, state):
    required = job["state_requirement"]

    if required:
        if not state:
            return [_reason("warn", "Your state is not recorded, so it could not be compared.")]
        if state == required:
            return [_reason("ok", f"State requirement matches: the post is for candidates of {required}.")]
        return [_reason("fail", f"State requirement not satisfied: the post is for candidates of "
                                f"{required}, but your state is {state}.")]

    if job["govt_category"] == "Andhra Pradesh" and state and state != "Andhra Pradesh":
        return [_reason("warn", "This is an Andhra Pradesh Government recruitment. Many state posts "
                                "have local or domicile rules, so check the official notification.")]
    return [_reason("ok", "No state restriction is stored for this post.")]


def _check_deadline(job, today):
    deadline = parse_date(job["application_deadline"])
    if deadline is None:
        return [_reason("info", "The application deadline has not been announced.")]
    if deadline < today:
        return [_reason("info", f"The application deadline ({format_date(deadline)}) has passed.")]
    return [_reason("info", f"Applications are open until {format_date(deadline)}.")]


# --------------------------------------------------------------------
# Main entry points
# --------------------------------------------------------------------
def check_job_eligibility(job, age, qualification_level, state, today=None):
    """Compare one profile with one job. See the module docstring for the result format."""
    today = today or date.today()

    reasons = []
    reasons += _check_qualification(job, qualification_level)
    reasons += _check_age(job, age)
    reasons += _check_state(job, state)
    reasons += _check_deadline(job, today)

    kinds = {r["kind"] for r in reasons}
    if "fail" in kinds:
        status = STATUS_NOT_ELIGIBLE
    elif "warn" in kinds:
        status = STATUS_VERIFY
    else:
        status = STATUS_ELIGIBLE

    result = {"status": status, "reasons": reasons}
    result.update(STATUS_DISPLAY[status])
    return result


def summarize_results(items):
    """Count results per status. items = [{'job': ..., 'result': {...}}, ...]"""
    counts = {STATUS_ELIGIBLE: 0, STATUS_VERIFY: 0, STATUS_NOT_ELIGIBLE: 0}
    for item in items:
        counts[item["result"]["status"]] += 1
    counts["total"] = len(items)
    return counts