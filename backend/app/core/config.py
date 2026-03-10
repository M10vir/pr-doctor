import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is missing. Set it in backend/.env")
