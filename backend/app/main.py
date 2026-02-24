from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from app.agents.reviewer import baseline_review
from app.agents.patcher import baseline_patch, docs_patch
from app.schemas.patch import PatchRequest
from app.schemas.review import ReviewResult
from app.schemas.fixpr import FixPRRequest
from app.agents.code_patcher import patch_demo_repo
from app.tools.github_tool import get_pr, get_pr_diff, get_pr_files, parse_pr_url, get_file_content, comment_on_pr, get_files_content_map, create_branch, create_pull_request, update_file
from app.agents.patch_apply import extract_new_files_by_blocks
from app.db.database import engine
from app.db.models import Run
from app.db.database import Base
import json
from sqlalchemy.orm import Session
from app.db.deps import get_db
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="PR Doctor", version="0.1.0")

def _get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # Local dev + preview defaults
    defaults = ["http://localhost:5173", "http://localhost:4173"]
    # Merge unique
    for d in defaults:
        if d not in origins:
            origins.append(d)
    return origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

STATUS_ORDER = {
    "created": 0,
    "analyzed": 1,
    "patched": 2,
    "commented": 3,
    "fix_pr_created": 4,
    "error": 99,
}

def _update_run(db, run_id: int, **fields):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail={"error": "run_not_found", "run_id": run_id})

    # ✅ Prevent status downgrade (e.g., patched -> analyzed)
    if "status" in fields and run.status:
        cur = STATUS_ORDER.get(run.status, 0)
        nxt = STATUS_ORDER.get(fields["status"], 0)
        if nxt < cur:
            fields.pop("status")

    for k, v in fields.items():
        setattr(run, k, v)

    run.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return run

class PRRequest(BaseModel):
    pr_url: HttpUrl
    run_id: Optional[int] = None

@app.get("/health")
def health():
    return {"status": "ok"}

class CreateRunRequest(BaseModel):
    pr_url: HttpUrl

@app.post("/runs")
async def create_run(req: CreateRunRequest, db: Session = Depends(get_db)):
    # create a run shell; actual analyze/patch will update it
    run = Run(pr_url=str(req.pr_url), status="created")
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "pr_url": run.pr_url, "status": run.status}

@app.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.id.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "pr_url": r.pr_url,
            "pr_title": r.pr_title,
            "status": r.status,
            "comment_url": r.comment_url,
            "fix_pr_url": r.fix_pr_url,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]

@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.query(Run).filter(Run.id == run_id).first()
    if not r:
        raise HTTPException(status_code=404, detail={"error": "run_not_found"})
    return {
        "id": r.id,
        "pr_url": r.pr_url,
        "pr_title": r.pr_title,
        "status": r.status,
        "review": json.loads(r.review_json or "{}"),
        "patch": json.loads(r.patch_json or "{}"),
        "comment_url": r.comment_url,
        "fix_pr_url": r.fix_pr_url,
        "error": json.loads(r.error_json or "{}"),
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }

@app.post("/github/pr")
async def github_pr(req: PRRequest):
    pr = await get_pr(str(req.pr_url))
    if isinstance(pr, dict) and pr.get("error"):
        raise HTTPException(status_code=pr.get("status_code", 400), detail=pr)

    return {
        "title": pr.get("title"),
        "state": pr.get("state"),
        "user": pr.get("user", {}).get("login"),
        "base": pr.get("base", {}).get("ref"),
        "head": pr.get("head", {}).get("ref"),
        "html_url": pr.get("html_url"),
    }

@app.post("/github/pr-diff")
async def github_pr_diff(req: PRRequest):
    res = await get_pr_diff(str(req.pr_url))
    if isinstance(res, dict) and res.get("error"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)

    diff = res["diff"]
    return {
        "pr_url": str(req.pr_url),
        "diff_chars": len(diff),
        "diff_preview": diff[:1200],
    } 

@app.post("/analyze-pr")
async def analyze_pr(req: PRRequest, db: Session = Depends(get_db)):
    pr = await get_pr(str(req.pr_url))
    if isinstance(pr, dict) and pr.get("error"):
        if req.run_id is not None:
            _update_run(db, req.run_id, status="error", error_json=json.dumps(pr))
        raise HTTPException(status_code=pr.get("status_code", 400), detail=pr)

    diff_res = await get_pr_diff(str(req.pr_url))
    if isinstance(diff_res, dict) and diff_res.get("error"):
        if req.run_id is not None:
            _update_run(db, req.run_id, status="error", pr_title=pr.get("title", ""), error_json=json.dumps(diff_res))
        raise HTTPException(status_code=diff_res.get("status_code", 400), detail=diff_res)

    diff_text = diff_res["diff"]
    review = baseline_review(diff_text)

    if req.run_id is not None:
        _update_run(
            db,
            req.run_id,
            pr_title=pr.get("title", ""),
            status="analyzed",
            review_json=json.dumps(review.model_dump()),
            error_json="{}",
        )

    return {
        "pr": {
            "title": pr.get("title"),
            "html_url": pr.get("html_url"),
            "user": pr.get("user", {}).get("login"),
            "state": pr.get("state"),
        },
        "review": review.model_dump(),
        "meta": {
            "diff_chars": len(diff_text),
        }
    }

@app.post("/generate-patch")
async def generate_patch(req: PatchRequest, db: Session = Depends(get_db)):
    pr = await get_pr(req.pr_url)
    if isinstance(pr, dict) and pr.get("error"):
        raise HTTPException(status_code=pr.get("status_code", 400), detail=pr)

    files = await get_pr_files(req.pr_url)
    # if error list returned
    if isinstance(files, list) and files and isinstance(files[0], dict) and files[0].get("error"):
        raise HTTPException(status_code=files[0].get("status_code", 400), detail=files[0])

    diff_res = await get_pr_diff(req.pr_url)
    if isinstance(diff_res, dict) and diff_res.get("error"):
        raise HTTPException(status_code=diff_res.get("status_code", 400), detail=diff_res)

    diff_text = diff_res["diff"]

    # Reuse reviewer output (baseline) for now
    review_obj = baseline_review(diff_text)

    # --- NEW: docs-only patch path ---
    is_docs_only = (
        len(files) > 0
        and all(str(f.get("filename", "")).endswith(".md") for f in files)
    )

    if is_docs_only:
        owner, repo, _ = parse_pr_url(req.pr_url)

        # Prefer head SHA for precise content
        head_sha = pr.get("head", {}).get("sha")
        md_path = files[0].get("filename")  # MVP: patch first file only

        file_res = await get_file_content(owner, repo, md_path, head_sha)
        if isinstance(file_res, dict) and file_res.get("error"):
            raise HTTPException(status_code=file_res.get("status_code", 400), detail=file_res)

        patch = docs_patch(md_path, file_res["content"])
    else:
        # If this is our demo repo, generate a real code patch
        owner, repo, _ = parse_pr_url(req.pr_url)

        if owner.lower() == "m10vir" and repo.lower() == "pr-doctor-demo-repo":
            files_map = await get_files_content_map(req.pr_url)
            if isinstance(files_map, dict) and files_map.get("error"):
                raise HTTPException(status_code=files_map.get("status_code", 400), detail=files_map)

            patch = patch_demo_repo(files_map)

        else:
            # fallback placeholder / baseline
            patch = baseline_patch(review_obj)

    if req.run_id is not None:
        _update_run(
            db,
            req.run_id,
            pr_title=pr.get("title", ""),
            status="patched",
            review_json=json.dumps(review_obj.model_dump()),
            patch_json=json.dumps(patch.model_dump()),
            error_json="{}",
        )

    return {
        "pr": {
            "title": pr.get("title"),
            "html_url": pr.get("html_url"),
        },
        "review": review_obj.model_dump(),
        "patch": patch.model_dump(),
        "changed_files_count": len(files),
        "changed_files_sample": [f.get("filename") for f in files[:8]],
        "docs_only": is_docs_only,
    }

@app.post("/comment-review")
async def comment_review(req: PRRequest, db: Session = Depends(get_db)):
    pr = await get_pr(str(req.pr_url))
    if isinstance(pr, dict) and pr.get("error"):
        raise HTTPException(status_code=pr.get("status_code", 400), detail=pr)

    diff_res = await get_pr_diff(str(req.pr_url))
    if isinstance(diff_res, dict) and diff_res.get("error"):
        raise HTTPException(status_code=diff_res.get("status_code", 400), detail=diff_res)

    review = baseline_review(diff_res["diff"])

    lines = [
        "## 🤖 PR Doctor Review (Baseline)",
        review.summary,
        "",
        f"**Overall risk:** `{review.overall_risk}`",
        "",
        "### Findings",
    ]
    if not review.findings:
        lines.append("- No findings.")
    else:
        for f in review.findings:
            lines.append(f"- **{f.category}** | `{f.severity}` | confidence `{f.confidence}` — {f.title}")
            lines.append(f"  - Recommendation: {f.recommendation}")

    body = "\n".join(lines)
    res = await comment_on_pr(str(req.pr_url), body)

    if res.get("error"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)

    if req.run_id is not None:
        _update_run(
            db,
            req.run_id,
            pr_title=pr.get("title", ""),
            comment_url=res.get("html_url", ""),
            status="commented",
        )

    return {"comment_url": res.get("html_url"), "status": "posted"}

@app.post("/open-fix-pr")
async def open_fix_pr(req: FixPRRequest, db: Session = Depends(get_db)):
    # 1) Get PR metadata
    pr = await get_pr(req.pr_url)
    if isinstance(pr, dict) and pr.get("error"):
        raise HTTPException(status_code=pr.get("status_code", 400), detail=pr)

    owner, repo, number = parse_pr_url(req.pr_url)
    base_branch = pr.get("base", {}).get("ref") or "main"
    head_sha = pr.get("head", {}).get("sha")

    if not head_sha:
        raise HTTPException(status_code=400, detail={"error": "missing_head_sha"})

    # 2) Generate patch using existing logic (demo patcher will fire)
    diff_res = await get_pr_diff(req.pr_url)
    if isinstance(diff_res, dict) and diff_res.get("error"):
        raise HTTPException(status_code=diff_res.get("status_code", 400), detail=diff_res)

    review_obj = baseline_review(diff_res["diff"])
    files_map = await get_files_content_map(req.pr_url)
    if isinstance(files_map, dict) and files_map.get("error"):
        raise HTTPException(status_code=files_map.get("status_code", 400), detail=files_map)

    patch = patch_demo_repo(files_map)
    if not patch.safe_to_apply or not patch.unified_diff.strip():
        raise HTTPException(status_code=400, detail={"error": "patch_not_applicable", "patch": patch.model_dump()})

    if req.run_id is not None:
        existing = db.query(Run).filter(Run.id == req.run_id).first()
        if existing and existing.fix_pr_url:
            return {
                "status": "already_has_fix_pr",
                "fix_pr_url": existing.fix_pr_url,
                "fix_branch": "",
                "updated_files": [],
            }

    # 3) Create new branch from PR head
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fix_branch = f"pr-doctor/fix-pr-{number}-{stamp}"

    br = await create_branch(owner, repo, fix_branch, head_sha)
    if isinstance(br, dict) and br.get("error"):
        raise HTTPException(status_code=br.get("status_code", 400), detail=br)

    # 4) Compute new file contents from patch + update files
    new_files = extract_new_files_by_blocks(patch.unified_diff)

    # For each file, we need its current SHA on the PR head
    # We can reuse get_file_content which returns sha
    updates = []
    for path, new_text in new_files.items():
        fr = await get_file_content(owner, repo, path, head_sha)
        if isinstance(fr, dict) and fr.get("error"):
            raise HTTPException(status_code=fr.get("status_code", 400), detail=fr)

        upd = await update_file(
            owner=owner,
            repo=repo,
            path=path,
            content_text=new_text,
            branch=fix_branch,
            sha=fr.get("sha"),
            message=f"PR Doctor: auto-fix {path}",
        )
        if isinstance(upd, dict) and upd.get("error"):
            raise HTTPException(status_code=upd.get("status_code", 400), detail=upd)
        updates.append({"path": path})

    # 5) Open Fix PR
    pr_title = f"PR Doctor Fix: Address security + quality issues (PR #{number})"
    pr_body = (
        f"This Fix PR was generated by **PR Doctor**.\n\n"
        f"Original PR: {pr.get('html_url')}\n\n"
        f"### Changes\n"
        f"- Remove hardcoded secret (use env var)\n"
        f"- Remove debug print\n"
        f"- Replace SQL string concatenation with parameterized pattern\n\n"
        f"### Review Summary\n"
        f"- Overall risk: {review_obj.overall_risk}\n"
        f"- Findings: {len(review_obj.findings)}\n"
    )

    newpr = await create_pull_request(
        owner=owner,
        repo=repo,
        title=pr_title,
        body=pr_body,
        head=fix_branch,
        base=base_branch,
    )
    if isinstance(newpr, dict) and newpr.get("error"):
        raise HTTPException(status_code=newpr.get("status_code", 400), detail=newpr)

    if req.run_id is not None:
        _update_run(
            db,
            req.run_id,
            pr_title=pr.get("title", ""),
            fix_pr_url=newpr.get("html_url", ""),
            status="fix_pr_created",
        )

    return {
        "status": "fix_pr_created",
        "fix_branch": fix_branch,
        "fix_pr_url": newpr.get("html_url"),
        "updated_files": updates,
    }
