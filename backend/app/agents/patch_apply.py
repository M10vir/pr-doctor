import re

def extract_new_file_contents_from_known_patch(unified_diff: str) -> dict:
    """
    MVP-safe for our demo patch format:
    We know our patch fully replaces app/config.py and app/user.py.
    We'll derive the *new file contents* from the added lines in each file block.
    """
    files = {}
    current_file = None
    collecting = False
    new_lines = []

    for line in unified_diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.replace("+++ b/", "").strip()
            collecting = True
            new_lines = []
            continue

        if line.startswith("--- a/"):
            continue

        if line.startswith("diff "):
            continue

        if current_file and collecting:
            # Skip hunk markers
            if line.startswith("@@"):
                continue
            # Added lines become new content
            if line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:])
            # For full-replacement patches this is enough for demo
            # (we're replacing the entire file with the added lines)
    # This simple parser needs file separation; handle by splitting on "+++ b/"
    # Instead: implement two-pass parse by blocks:

def extract_new_files_by_blocks(unified_diff: str) -> dict:
    files = {}
    blocks = unified_diff.split("\n--- a/")
    for b in blocks:
        if not b.strip():
            continue
        # b starts like: "app/config.py\n+++ b/app/config.py\n@@ ..."
        m_to = re.search(r"\+\+\+ b/(.+)", b)
        if not m_to:
            continue
        path = m_to.group(1).strip()
        new_lines = []
        for ln in b.splitlines():
            if ln.startswith("+++ ") or ln.startswith("--- ") or ln.startswith("@@"):
                continue
            if ln.startswith("+") and not ln.startswith("+++"):
                new_lines.append(ln[1:])
        files[path] = "\n".join(new_lines).rstrip() + "\n"
    return files
