import difflib
import re
from app.schemas.patch import PatchResult
from app.schemas.review import ReviewResult

def _clean_md(text: str) -> str:
    # Minimal safe fixes:
    # - remove trailing spaces
    # - normalize multiple blank lines (max 2)
    # - fix common typos (tiny set)
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.replace("teh ", "the ")
    cleaned = cleaned.replace("alot", "a lot")
    return cleaned + ("\n" if not cleaned.endswith("\n") else "")

def docs_patch(path: str, old_text: str) -> PatchResult:
    new_text = _clean_md(old_text)

    if new_text == old_text:
        return PatchResult(
            description="No safe doc improvements detected (already clean).",
            unified_diff="",
            safe_to_apply=False,
            target_file=path,
        )

    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )

    return PatchResult(
        description="Applied safe markdown cleanup (whitespace/format/typo normalization).",
        unified_diff="".join(diff),
        safe_to_apply=True,
        target_file=path,
    )

def baseline_patch(review: ReviewResult) -> PatchResult:
    """
    Baseline patcher fallback: returns a placeholder unified diff.
    Used when PR is not docs-only (until LLM patcher is added).
    """
    desc = "Suggested adding/adjusting a small test to cover the change. Baseline patch is a placeholder."
    diff = (
        "--- a/README_PR_DOCTOR_PATCH.txt\n"
        "+++ b/README_PR_DOCTOR_PATCH.txt\n"
        "@@ -0,0 +1,6 @@\n"
        "+PR Doctor Patch Suggestion (Placeholder)\n"
        "+\n"
        "+Finding: No test changes detected\n"
        "+Recommendation: Add/update tests to cover the change.\n"
        "+\n"
        "+Next: LLM patcher will generate repo-specific updates.\n"
    )

    return PatchResult(
        description=desc,
        unified_diff=diff,
        safe_to_apply=False,
        target_file=None,
    )
