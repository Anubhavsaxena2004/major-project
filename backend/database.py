import os
import sqlite3
from pathlib import Path
from typing import Any

from backend.config import settings

DB_PATH = Path(settings.database_url.replace("sqlite:///", "", 1)) if settings.database_url.startswith("sqlite") else Path("data") / "lecture_packages.db"


def initialize_db() -> None:
    if settings.database_url.startswith("sqlite"):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lecture_packages (
                    lecture_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    package_dir TEXT NOT NULL,
                    duration REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        return

    if settings.database_url.startswith("postgres"):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for PostgreSQL DATABASE_URL support") from exc

        with psycopg.connect(settings.database_url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lecture_packages (
                    lecture_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    package_dir TEXT NOT NULL,
                    duration DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.commit()
        return

    raise RuntimeError(f"Unsupported DATABASE_URL value: {settings.database_url}")


def upsert_lecture(lecture_id: str, title: str, source_url: str, package_dir: str, duration: float) -> None:
    initialize_db()

    if settings.database_url.startswith("sqlite"):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO lecture_packages (lecture_id, title, source_url, package_dir, duration, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(lecture_id) DO UPDATE SET
                    title = excluded.title,
                    source_url = excluded.source_url,
                    package_dir = excluded.package_dir,
                    duration = excluded.duration,
                    created_at = datetime('now')
                """,
                (lecture_id, title, source_url, package_dir, duration),
            )
            conn.commit()
        return

    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lecture_packages (lecture_id, title, source_url, package_dir, duration, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (lecture_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_url = EXCLUDED.source_url,
                    package_dir = EXCLUDED.package_dir,
                    duration = EXCLUDED.duration,
                    created_at = NOW()
                """,
                (lecture_id, title, source_url, package_dir, duration),
            )
        conn.commit()


def list_lectures() -> list[dict[str, Any]]:
    initialize_db()

    if settings.database_url.startswith("sqlite"):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT lecture_id, title, source_url, package_dir, duration, created_at FROM lecture_packages ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT lecture_id, title, source_url, package_dir, duration, created_at FROM lecture_packages ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()

    return [
        {
            "lecture_id": lecture_id,
            "title": title,
            "source_url": source_url,
            "package_dir": package_dir,
            "duration": duration,
            "created_at": created_at,
        }
        for lecture_id, title, source_url, package_dir, duration, created_at in rows
    ]
