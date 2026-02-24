from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.database import Base

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pr_url: Mapped[str] = mapped_column(String(500), index=True)
    pr_title: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(50), default="created")  # analyzed / patched / fix_pr_created / error
    review_json: Mapped[str] = mapped_column(Text, default="{}")
    patch_json: Mapped[str] = mapped_column(Text, default="{}")
    comment_url: Mapped[str] = mapped_column(String(500), default="")
    fix_pr_url: Mapped[str] = mapped_column(String(500), default="")
    error_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
