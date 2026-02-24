from pydantic import BaseModel, Field
from typing import Optional

class PatchRequest(BaseModel):
    pr_url: str
    finding_index: int = Field(default=0, ge=0)
    run_id: Optional[int] = None

class PatchResult(BaseModel):
    patch_type: str = "unified_diff"
    target_file: Optional[str] = None
    description: str
    unified_diff: str
    safe_to_apply: bool = True
