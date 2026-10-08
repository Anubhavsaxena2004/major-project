from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import list_lectures, upsert_lecture
from backend.lecture_pipeline import generate_lecture_package, generate_lecture_package_from_file

BASE_DIR = Path(__file__).resolve().parent.parent
PACKAGES_DIR = Path(settings.lecture_output_root)
UPLOAD_DIR = Path(settings.upload_dir)
DEMO_DIR = BASE_DIR / "demo"

app = FastAPI(title="BandwidthBridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/packages", StaticFiles(directory=str(PACKAGES_DIR)), name="packages")
app.mount("/demo", StaticFiles(directory=str(DEMO_DIR)), name="demo")


@app.get("/")
def root() -> dict:
    return {"service": "BandwidthBridge", "status": "running", "database": settings.database_url}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


def sync_disk_packages() -> None:
    if not PACKAGES_DIR.exists():
        return
    for item in PACKAGES_DIR.iterdir():
        if item.is_dir():
            manifest_file = item / "manifest.json"
            if manifest_file.exists():
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    lecture_id = str(data.get("lectureId") or item.name)
                    duration = float(data.get("duration", 0))
                    title = str(data.get("title") or lecture_id.replace("-", " ").title())
                    upsert_lecture(
                        lecture_id=lecture_id,
                        title=title,
                        source_url=f"/packages/{lecture_id}",
                        package_dir=str(item),
                        duration=duration,
                    )
                except Exception:
                    pass


@app.get("/api/lectures")
def list_generated_lectures() -> list[dict]:
    sync_disk_packages()
    return list_lectures()


@app.get("/api/lectures/{lecture_id}/manifest")
def get_manifest(lecture_id: str) -> dict:
    manifest_path = PACKAGES_DIR / lecture_id / "manifest.json"

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Lecture '{lecture_id}' not found")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


@app.post("/api/lectures/generate")
async def generate_lecture(request: Request, file: UploadFile | None = None) -> dict:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type.lower():
        payload = await request.json()
        url = payload.get("url")
        lecture_id = payload.get("lecture_id")
        max_duration = payload.get("max_duration")
        source_type = payload.get("source_type", "youtube")
    else:
        form = await request.form()
        url = form.get("url")
        lecture_id = form.get("lecture_id")
        max_duration = form.get("max_duration")
        source_type = form.get("source_type", "youtube")
        file = form.get("file") if "file" in form else None

    if source_type == "local":
        if file is None and url and Path(str(url)).exists():
            source_path = Path(str(url))
        elif file is not None:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            upload_name = f"{uuid.uuid4()}_{file.filename or 'upload.mp4'}"
            source_path = UPLOAD_DIR / upload_name
            source_path.write_bytes(await file.read())
        else:
            raise HTTPException(status_code=400, detail="A local video file is required when source_type is 'local'.")

        try:
            result = await asyncio.to_thread(
                generate_lecture_package_from_file,
                video_path=source_path,
                lecture_id=lecture_id,
                output_root=PACKAGES_DIR,
                max_duration=float(max_duration) if max_duration not in (None, "") else None,
            )
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        if not url or not str(url).strip():
            raise HTTPException(status_code=400, detail="A valid lecture URL is required.")

        try:
            result = await asyncio.to_thread(
                generate_lecture_package,
                video_url=str(url),
                lecture_id=lecture_id,
                output_root=PACKAGES_DIR,
                max_duration=float(max_duration) if max_duration not in (None, "") else None,
            )
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    upsert_lecture(
        lecture_id=result["lectureId"],
        title=result["title"],
        source_url=result["sourceUrl"],
        package_dir=result["packageDir"],
        duration=float(result["duration"]),
    )

    return {
        "ok": True,
        "lectureId": result["lectureId"],
        "title": result["title"],
        "duration": result["duration"],
        "packageDir": result["packageDir"],
        "manifestUrl": f"/api/lectures/{result['lectureId']}/manifest",
        "sourceType": source_type,
    }
