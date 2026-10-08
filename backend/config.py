from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'lecture_packages.db'}")
    lecture_output_root: str = os.getenv("LECTURE_OUTPUT_ROOT", str(BASE_DIR / "packages"))
    upload_dir: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))


settings = Settings()
