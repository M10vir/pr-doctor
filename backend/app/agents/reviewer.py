import re
from app.schemas.review import ReviewResult, Finding

def _first_added_line(diff_text: str, needle_regex: str) -> tuple[str | None, str | None]:
    """
    Best-effort: find the first added line matching needle_regex and return (file, line_hint).
    Works on unified diffs by tracking current file header and hunk header.
    """
    current_file = None
    current_hunk = None

    for line in diff_text.splitlines():
        # file headers
        if line.startswith("+++ b/"):
            current_file = line.replace("+++ b/", "").strip()
        # hunk headers, e.g. @@ -1,3 +1,9 @@
        elif line.startswith("@@ "):
            current_hunk = line.strip()

        # only check added lines (avoid context / removed lines)
        if line.startswith("+") and not line.startswith("+++"):
            if re.search(needle_regex, line):
                return current_file, current_hunk

    return None, None

def baseline_review(diff_text: str) -> ReviewResult:
    findings = []

    # -------------------
    # Secrets / credentials
    # -------------------
    secret_hit = (
        re.search(r"AKIA[0-9A-Z]{16}", diff_text) or
        re.search(r"\bSECRET\b", diff_text) or
        re.search(r"\bPASSWORD\b", diff_text) or
        re.search(r"API_KEY\s*=\s*['\"][^'\"]+['\"]", diff_text)
    )
    if secret_hit:
        f, h = _first_added_line(diff_text, r"(AKIA[0-9A-Z]{16}|\bSECRET\b|\bPASSWORD\b|API_KEY\s*=)")
        findings.append(Finding(
            category="security",
            severity="critical",
            confidence=0.80,
            file=f,
            line_hint=h,
            title="Possible secret/token in diff",
            recommendation="Remove secrets from code. Use environment variables or a secret manager. If exposed, rotate credentials immediately.",
        ))

    # -------------------
    # TODO / FIXME
    # -------------------
    if "TODO" in diff_text or "FIXME" in diff_text:
        f, h = _first_added_line(diff_text, r"\b(TODO|FIXME)\b")
        findings.append(Finding(
            category="quality",
            severity="medium",
            confidence=0.65,
            file=f,
            line_hint=h,
            title="TODO/FIXME left in code",
            recommendation="Resolve the TODO/FIXME before merge or convert it into a tracked issue and remove it from the code path.",
        ))

    # -------------------
    # Debug logging (only if added)
    # -------------------
    # Prefer checking added lines to reduce false positives
    f, h = _first_added_line(diff_text, r"(print\(|console\.log\()")
    if f or h:
        findings.append(Finding(
            category="quality",
            severity="low",
            confidence=0.75,
            file=f,
            line_hint=h,
            title="Debug logging detected",
            recommendation="Remove debug prints/logs or replace with structured logging at an appropriate level.",
        ))

    # -------------------
    # SQL injection (string concatenation into SQL)
    # -------------------
    # Detect patterns like: "SELECT ... WHERE id=" + user_input
    sql_injection_pattern = r"(SELECT|INSERT|UPDATE|DELETE).*(WHERE|VALUES|SET).*(\"|')\s*\+\s*[a-zA-Z_][a-zA-Z0-9_]*"
    if re.search(sql_injection_pattern, diff_text, re.IGNORECASE):
        f, h = _first_added_line(diff_text, sql_injection_pattern)
        findings.append(Finding(
            category="security",
            severity="high",
            confidence=0.70,
            file=f,
            line_hint=h,
            title="Possible SQL injection via string concatenation",
            recommendation="Use parameterized queries / prepared statements. Never concatenate user input into SQL strings.",
        ))

    # -------------------
    # Tests missing (basic signal)
    # -------------------
    if "pytest" not in diff_text.lower() and "test" not in diff_text.lower():
        findings.append(Finding(
            category="tests",
            severity="medium",
            confidence=0.55,
            file=None,
            line_hint=None,
            title="No test changes detected",
            recommendation="Consider adding or updating tests to cover the change, especially for logic/security-related changes.",
        ))

    # -------------------
    # Risk scoring
    # -------------------
    risk = "low"
    if any(f.severity in ["high", "critical"] for f in findings):
        risk = "high"
    elif any(f.severity == "medium" for f in findings):
        risk = "medium"

    summary = (
        f"Reviewed diff and found {len(findings)} potential issue(s). "
        "This is a baseline reviewer; LLM-based reviewer will increase precision."
    )

    return ReviewResult(summary=summary, overall_risk=risk, findings=findings) 
