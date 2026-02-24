import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is missing. Set it in backend/.env")
