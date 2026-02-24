import difflib
from app.schemas.patch import PatchResult

def patch_demo_repo(files: dict) -> PatchResult:
    """
    Generates a safe unified diff for the demo repo:
    - app/config.py: replace hardcoded API_KEY with env var
    - app/user.py: remove print, remove SQL concatenation, return parameterized query pattern
    """
    if "app/config.py" not in files or "app/user.py" not in files:
        return PatchResult(
            description="Demo patcher expects app/config.py and app/user.py",
            unified_diff="",
            safe_to_apply=False,
            target_file=None,
        )

    old_cfg = files["app/config.py"]
    old_user = files["app/user.py"]

    new_cfg = (
        "import os\n\n"
        "API_KEY = os.getenv(\"API_KEY\", \"\")\n"
        "if not API_KEY:\n"
        "    raise RuntimeError(\"API_KEY is missing. Set it via environment variables or a secret manager.\")\n"
    )

    new_user = (
        "def get_user(user_id):\n"
        "    # Safe pattern: parameterized queries (example placeholder)\n"
        "    query = \"SELECT * FROM users WHERE id = %s\"\n"
        "    params = (user_id,)\n"
        "    return query, params\n"
    )

    diff_cfg = difflib.unified_diff(
        old_cfg.splitlines(keepends=True),
        new_cfg.splitlines(keepends=True),
        fromfile="a/app/config.py",
        tofile="b/app/config.py",
    )
    diff_user = difflib.unified_diff(
        old_user.splitlines(keepends=True),
        new_user.splitlines(keepends=True),
        fromfile="a/app/user.py",
        tofile="b/app/user.py",
    )

    unified = "".join(diff_cfg) + "\n" + "".join(diff_user)

    return PatchResult(
        description="Removed hardcoded secret, removed debug print, and replaced SQL concatenation with a parameterized query pattern.",
        unified_diff=unified,
        safe_to_apply=True,
        target_file=None,
    )
