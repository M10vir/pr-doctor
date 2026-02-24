from typing import Optional
from pydantic import BaseModel
from app.schemas.patch import PatchResult

class FixPRRequest(BaseModel):
    pr_url: str
    run_id: Optional[int] = None
