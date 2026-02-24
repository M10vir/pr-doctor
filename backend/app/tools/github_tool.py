import httpx
import base64
from datetime import datetime
from app.core.config import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"

def _headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pr-doctor",
    }

def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    parts = pr_url.strip().split("?")[0].strip("/").split("/")
    owner = parts[-4]
    repo = parts[-3]
    if parts[-2] != "pull":
        raise ValueError("Invalid PR URL. Expected .../pull/<number>")
    number = int(parts[-1])
    return owner, repo, number

async def get_pr(pr_url: str) -> dict:
    owner, repo, number = parse_pr_url(pr_url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
            headers=_headers(),
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:500],
                "endpoint": f"/repos/{owner}/{repo}/pulls/{number}",
            }
        return r.json()

async def get_pr_diff(pr_url: str) -> dict:
    owner, repo, number = parse_pr_url(pr_url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
            headers={**_headers(), "Accept": "application/vnd.github.v3.diff"},
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:500],
                "endpoint": f"/repos/{owner}/{repo}/pulls/{number}",
            }
        return {"diff": r.text} 

async def get_pr_files(pr_url: str) -> list[dict]:
    owner, repo, number = parse_pr_url(pr_url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/files",
            headers=_headers(),
            params={"per_page": 100},
        )
        if r.status_code >= 400:
            return [{
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:500],
                "endpoint": f"/repos/{owner}/{repo}/pulls/{number}/files",
            }]
        return r.json()

async def get_file_content(owner: str, repo: str, path: str, ref: str) -> dict:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            params={"ref": ref},
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:500],
                "endpoint": f"/repos/{owner}/{repo}/contents/{path}",
            }
        data = r.json()
        if data.get("encoding") == "base64" and "content" in data:
            decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return {"path": path, "content": decoded, "sha": data.get("sha")}
        return {"path": path, "content": "", "sha": data.get("sha")}

async def get_files_content_map(pr_url: str) -> dict:
    owner, repo, number = parse_pr_url(pr_url)

    pr = await get_pr(pr_url)
    if isinstance(pr, dict) and pr.get("error"):
        return pr

    head_sha = pr.get("head", {}).get("sha")
    files = await get_pr_files(pr_url)
    if isinstance(files, list) and files and isinstance(files[0], dict) and files[0].get("error"):
        return files[0]

    out = {}
    for f in files:
        path = f.get("filename")
        if not path:
            continue
        fr = await get_file_content(owner, repo, path, head_sha)
        if isinstance(fr, dict) and fr.get("error"):
            return fr
        out[path] = fr["content"]
    return out

async def comment_on_pr(pr_url: str, body: str) -> dict:
    owner, repo, number = parse_pr_url(pr_url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments",
            headers=_headers(),
            json={"body": body},
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:500],
                "endpoint": f"/repos/{owner}/{repo}/issues/{number}/comments",
            }
        return r.json()

async def create_branch(owner: str, repo: str, new_branch: str, from_sha: str) -> dict:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:800],
                "endpoint": f"/repos/{owner}/{repo}/git/refs",
            }
        return r.json()

async def update_file(owner: str, repo: str, path: str, content_text: str, branch: str, sha: str, message: str) -> dict:
    encoded = base64.b64encode(content_text.encode("utf-8")).decode("utf-8")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            json={
                "message": message,
                "content": encoded,
                "branch": branch,
                "sha": sha,
            },
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:800],
                "endpoint": f"/repos/{owner}/{repo}/contents/{path}",
            }
        return r.json()

async def create_pull_request(owner: str, repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(),
            json={"title": title, "body": body, "head": head, "base": base},
        )
        if r.status_code >= 400:
            return {
                "error": "github_api_error",
                "status_code": r.status_code,
                "message": r.text[:800],
                "endpoint": f"/repos/{owner}/{repo}/pulls",
            }
        return r.json()
